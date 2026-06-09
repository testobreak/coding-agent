# runtime/execution_engine.py

from typing import Any, List
from planning.task_status import TaskStatus
from planning.task_types import TaskType
from execution.execution_state import ExecutionState
from execution.verification_result import VerificationPlan, VerificationResult

class ExecutionEngine:
    def __init__(self, executor, state_manager):
        self.executor = executor
        self.state_manager = state_manager
        
        from execution.verification_engine import VerificationEngine
        from planning.repair_engine import RepairEngine
        from memory.experience_store import ExecutionMemory
        from planning.workers import (
            RetrievalWorker,
            AnalysisWorker,
            EditWorker,
            ValidationWorker,
            RepairWorker
        )
        
        self.verification_engine = VerificationEngine(
            file_manager=self.executor.file_manager,
            state_manager=self.state_manager,
            validator=self.executor.validator,
            compile_validator=self.executor.compile_validator,
            test_runner=self.executor.tests,
            impact_analyzer=self.executor.impact_analyzer
        )
        self.repair_engine = RepairEngine(llm=self.executor.modifier.llm, max_attempts=3)
        self.execution_memory = ExecutionMemory()
        
        self.workers = {
            TaskType.RETRIEVE_CONTEXT: RetrievalWorker(self.executor, self.verification_engine),
            TaskType.ANALYZE_FAILURE: AnalysisWorker(self.executor, self.verification_engine),
            TaskType.MODIFY_SYMBOL: EditWorker(self.executor, self.verification_engine),
            TaskType.CREATE_SYMBOL: EditWorker(self.executor, self.verification_engine),
            TaskType.DELETE_SYMBOL: EditWorker(self.executor, self.verification_engine),
            TaskType.UPDATE_TEST: EditWorker(self.executor, self.verification_engine),
            TaskType.RUN_TEST: ValidationWorker(self.executor, self.verification_engine),
            TaskType.VERIFY_BUILD: ValidationWorker(self.executor, self.verification_engine),
            TaskType.VERIFY_TESTS: ValidationWorker(self.executor, self.verification_engine),
            TaskType.VERIFY_LINT: ValidationWorker(self.executor, self.verification_engine),
            TaskType.REPAIR_IMPORTS: RepairWorker(self.executor, self.verification_engine),
            TaskType.REPAIR_COMPILATION: RepairWorker(self.executor, self.verification_engine),
            TaskType.REPAIR_SYMBOL: RepairWorker(self.executor, self.verification_engine),
            TaskType.REPAIR_FAILURE: RepairWorker(self.executor, self.verification_engine),
        }

    def run(self):
        """
        Execute ready tasks from the ExecutionPlan DAG concurrently,
        enforcing mutual exclusion on file paths.
        """
        plan = self.state_manager.get_execution_plan()
        if not plan:
            return self._run_legacy()
        
        # Initialize execution memory episode
        self.execution_memory.start_episode(
            goal=plan.goal,
            plan_id=plan.plan_id,
            repository_id="com.hrms"
        )
        if not hasattr(self, "_logged_plans") or plan.plan_id not in self._logged_plans:
            if not hasattr(self, "_logged_plans"):
                self._logged_plans = set()
            self._logged_plans.add(plan.plan_id)
            self.execution_memory.log_plan(plan.plan_id, "modify_symbol", plan.to_dict())
        
        if plan.is_finished():
            outcome = "SUCCESS" if plan.is_successful() else "FAILED"
            self.execution_memory.complete_episode(plan.plan_id, outcome)
            return None
            
        from planning.graph_scheduler import GraphScheduler
        scheduler = GraphScheduler(plan)
        
        # Ensure stages are initialized on execution plan
        if not plan.stages:
            plan.stages = scheduler.build_execution_stages()
            self.state_manager.set_execution_plan(plan)
            self.state_manager.save_state()

        # Find the first stage that is not fully completed/skipped
        active_stage = None
        for stage in plan.stages:
            stage_finished = True
            for tid in stage.parallel_tasks:
                t = plan.find_task(tid)
                if t and t.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    stage_finished = False
                    break
            if not stage_finished:
                active_stage = stage
                break

        if not active_stage:
            print("[ExecutionEngine] All execution stages are finished.")
            if plan.is_finished():
                outcome = "SUCCESS" if plan.is_successful() else "FAILED"
                self.execution_memory.complete_episode(plan.plan_id, outcome)
            return None

        # Filter the scheduler's next runnable tasks to only include those in the active stage
        scheduler_runnable = scheduler.next_tasks()
        runnable_tasks = [t for t in scheduler_runnable if t.id in active_stage.parallel_tasks]
        
        if not runnable_tasks:
            running_tasks = [tid for tid in active_stage.parallel_tasks if plan.find_task(tid) and plan.find_task(tid).status == TaskStatus.RUNNING]
            if running_tasks:
                print(f"[ExecutionEngine] Waiting for active stage '{active_stage.stage_id}' tasks to complete: {running_tasks}")
            else:
                print(f"[ExecutionEngine] Active stage '{active_stage.stage_id}' blocked or wait-gated.")
            return None
            
        print(f"[ExecutionEngine] Scheduling {len(runnable_tasks)} tasks for parallel execution from stage '{active_stage.stage_id}'...")
        
        # Mark all selected tasks as RUNNING and save state before executing
        for task in runnable_tasks:
            scheduler.mark_started(task.id)
            # Log task started event
            self.execution_memory.log_event(plan.plan_id, "TASK_STARTED", {
                "task_id": task.id,
                "type": task.type.value,
                "description": task.description
            })
            
        self.state_manager.set_execution_plan(plan)
        self.state_manager.save_state()
        
        # Execute tasks in parallel using ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor
        
        # Helper execution function
        def worker_exec(t):
            try:
                res = self.execute_task_via_worker(t, plan)
                return t.id, True, res, ""
            except Exception as e:
                import traceback
                traceback.print_exc()
                return t.id, False, None, str(e)
                
        results = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_task = {executor.submit(worker_exec, t): t for t in runnable_tasks}
            for future in future_to_task:
                tid, success, res, err = future.result()
                results[tid] = (success, res, err)
                
        # Process outcomes synchronously after execution
        # Re-fetch plan and scheduler to ensure fresh references
        plan = self.state_manager.get_execution_plan()
        scheduler = GraphScheduler(plan)
        
        for task in plan.tasks:
            if task.id not in results:
                continue
                
            success, result, error_msg = results[task.id]
            
            # Additional result checking for validation results
            if success and isinstance(result, VerificationResult):
                success = result.success
                if not success:
                    error_msg = f"Verification failed with {len(result.diagnostics)} diagnostics."
            elif success and isinstance(result, dict) and not result.get("success", False):
                success = False
                error_msg = result.get("error", "Task execution failed.")
                
            if success:
                print(f"[ExecutionEngine] Task {task.id} COMPLETED successfully.")
                scheduler.mark_completed(task.id)
                state = self.state_manager.get_state()
                if task.id not in state.completed_steps:
                    state.completed_steps.append(task.id)
                    
                self.execution_memory.log_event(plan.plan_id, "TASK_COMPLETED", {
                    "task_id": task.id,
                    "status": "COMPLETED",
                    "success": True
                })
                if task.type in (TaskType.REPAIR_IMPORTS, TaskType.REPAIR_COMPILATION, TaskType.REPAIR_SYMBOL, TaskType.REPAIR_FAILURE):
                    self.execution_memory.log_repair(
                        episode_id=plan.plan_id,
                        repair_type=task.type.value,
                        target=task.target_symbol,
                        description=task.description,
                        success=True
                    )
            else:
                print(f"[ExecutionEngine] Task {task.id} FAILED: {error_msg}")
                
                self.execution_memory.log_event(plan.plan_id, "TASK_COMPLETED", {
                    "task_id": task.id,
                    "status": "FAILED",
                    "success": False,
                    "error": error_msg
                })
                
                # If it's a verification task failure, invoke repair planner
                if isinstance(result, VerificationResult) and not result.success:
                    # Log failures to failure record
                    for diag in result.diagnostics:
                        self.execution_memory.log_failure(
                            episode_id=plan.plan_id,
                            failure_type=diag.type,
                            file_path=diag.file_path,
                            line=diag.line,
                            symbol=diag.symbol,
                            message=diag.message
                        )
                        
                    # Enforce retry budget using RepairEngine
                    if not self.repair_engine.check_budget(plan):
                        print(f"[ExecutionEngine] Repair budget exhausted ({self.repair_engine.get_attempts(plan.plan_id)} attempts). Failing task {task.id}.")
                        scheduler.mark_failed(task.id)
                        state = self.state_manager.get_state()
                        if task.id not in state.failed_steps:
                            state.failed_steps.append(task.id)
                    else:
                        print("[ExecutionEngine] Verification failed. Invoking RepairEngine...")
                        repair_tasks = self.repair_engine.repair(result, plan.goal, key=plan.plan_id)
                        
                        if repair_tasks:
                            print(f"[ExecutionEngine] Injecting {len(repair_tasks)} repair tasks into the DAG.")
                            self.state_manager.set_execution_state(ExecutionState.REPAIRING.value)
                            
                            # Insert repair nodes as dependencies of the verification task
                            scheduler.insert_new_tasks(repair_tasks)
                            
                            for rep in repair_tasks:
                                # Log planning/generation of repair
                                self.execution_memory.log_repair(
                                    episode_id=plan.plan_id,
                                    repair_type=rep.type.value,
                                    target=rep.target_symbol,
                                    description=rep.description,
                                    success=True
                                )
                                
                            # Make this verification task depend on the new repair tasks
                            task.dependencies = list(set(task.dependencies + [rep.id for rep in repair_tasks]))
                            # Re-queue the verification task so it runs again after repairs
                            task.status = TaskStatus.PENDING
                            task.retries = 0
                            
                            # Regenerate plan stages topologically after mutations
                            plan.stages = scheduler.build_execution_stages()
                        else:
                            print("[ExecutionEngine] No repair tasks generated. Marking task as FAILED.")
                            scheduler.mark_failed(task.id)
                            state = self.state_manager.get_state()
                            if task.id not in state.failed_steps:
                                state.failed_steps.append(task.id)
                else:
                    # Standard task retries
                    if scheduler.can_retry(task.id):
                        scheduler.increment_retries(task.id)
                        print(f"[ExecutionEngine] Retrying task {task.id} (Attempt {task.retries}/{task.max_retries})")
                    else:
                        print(f"[ExecutionEngine] Max retries exceeded. Marking task {task.id} as FAILED.")
                        scheduler.mark_failed(task.id)
                        state = self.state_manager.get_state()
                        if task.id not in state.failed_steps:
                            state.failed_steps.append(task.id)
                            
        self.state_manager.set_execution_plan(plan)
        self.state_manager.save_state()
        
        # Check if plan is finished now to immediately log episode completion
        if plan.is_finished():
            outcome = "SUCCESS" if plan.is_successful() else "FAILED"
            self.execution_memory.complete_episode(plan.plan_id, outcome)
            
        last_task_id = runnable_tasks[-1].id
        return results[last_task_id][1] if last_task_id in results else None

    def execute_task_via_worker(self, task, plan) -> Any:
        worker = self.workers.get(task.type)
        if worker:
            return worker.execute(task, plan)
            
        # Fallbacks for specific transaction or verify changes
        if task.type == TaskType.COMMIT_TRANSACTION:
            return self.executor.dispatch("git_commit", {"message": f"Complete task DAG: {plan.goal}"})
        elif task.type == TaskType.VERIFY_CHANGES:
            return self.executor.dispatch("git_diff", {})
            
        raise ValueError(f"Unsupported task type: {task.type}")

    def _run_legacy(self):
        pending = self.state_manager.get_pending_executions()
        if not pending:
            return None
            
        execution = pending[0]
        if isinstance(execution, dict):
            execution["status"] = "running"
            
        result = self.executor.execute(execution)
        completed = self.state_manager.pop_next_execution()
        state = self.state_manager.get_state()
        action_id = completed.get("action_id") if isinstance(completed, dict) else None
        
        if isinstance(result, dict) and result.get("success", False):
            if action_id:
                state.completed_steps.append(action_id)
        else:
            if action_id:
                state.failed_steps.append(action_id)
            if completed and hasattr(self.state_manager, "retry_execution"):
                retries = completed.get("retries", 0)
                max_retries = completed.get("max_retries", 3)
                if retries < max_retries:
                    self.state_manager.retry_execution(completed)
                    
        self.state_manager.save_state()
        return result
