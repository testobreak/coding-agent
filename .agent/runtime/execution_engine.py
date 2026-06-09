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

    def run(self):
        """
        Execute the next ready task from the ExecutionPlan DAG.
        If no ExecutionPlan exists, falls back to legacy action queue runner.
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
            
        runnable_tasks = plan.get_runnable_tasks()
        if not runnable_tasks:
            print("[ExecutionEngine] No runnable tasks left in the plan.")
            return None
            
        # Select the first runnable task
        task = runnable_tasks[0]
        
        # 1. Update State Machine
        if task.type in (TaskType.VERIFY_BUILD, TaskType.RUN_TEST, TaskType.VERIFY_TESTS, TaskType.VERIFY_LINT, TaskType.VERIFY_CHANGES):
            self.state_manager.set_execution_state(ExecutionState.VERIFYING.value)
        elif task.type in (TaskType.REPAIR_IMPORTS, TaskType.REPAIR_COMPILATION, TaskType.REPAIR_SYMBOL, TaskType.REPAIR_FAILURE):
            self.state_manager.set_execution_state(ExecutionState.REPAIRING.value)
        else:
            self.state_manager.set_execution_state(ExecutionState.EXECUTING.value)
            
        task.status = TaskStatus.RUNNING
        self.state_manager.set_execution_plan(plan)
        self.state_manager.save_state()
        
        print(f"\n[ExecutionEngine] Running task: {task.id} ({task.type.value}) - {task.description}")
        
        success = False
        result = None
        error_msg = ""
        
        # Log task started event
        self.execution_memory.log_event(plan.plan_id, "TASK_STARTED", {
            "task_id": task.id,
            "type": task.type.value,
            "description": task.description
        })
        
        try:
            result = self.execute_task(task, plan)
            
            # Check for verification result specifically
            if isinstance(result, VerificationResult):
                success = result.success
                if not success:
                    # We have diagnostics to handle
                    error_msg = f"Verification failed with {len(result.diagnostics)} diagnostics."
            elif isinstance(result, dict) and not result.get("success", False):
                success = False
                error_msg = result.get("error", "Task execution failed.")
            else:
                success = True
        except Exception as e:
            import traceback
            traceback.print_exc()
            success = False
            error_msg = str(e)
            
        if success:
            print(f"[ExecutionEngine] Task {task.id} COMPLETED successfully.")
            plan.mark_completed(task.id)
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
                    plan.mark_failed(task.id)
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
                        for rep in repair_tasks:
                            rep.id = f"repair_{len(plan.tasks)}_{rep.type.value}"
                            plan.tasks.append(rep)
                            
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
                    else:
                        print("[ExecutionEngine] No repair tasks generated. Marking task as FAILED.")
                        plan.mark_failed(task.id)
                        state = self.state_manager.get_state()
                        if task.id not in state.failed_steps:
                            state.failed_steps.append(task.id)
            else:
                # Standard task retries
                if task.retries < task.max_retries:
                    task.retries += 1
                    task.status = TaskStatus.PENDING
                    print(f"[ExecutionEngine] Retrying task {task.id} (Attempt {task.retries}/{task.max_retries})")
                else:
                    print(f"[ExecutionEngine] Max retries exceeded. Marking task {task.id} as FAILED.")
                    plan.mark_failed(task.id)
                    state = self.state_manager.get_state()
                    if task.id not in state.failed_steps:
                        state.failed_steps.append(task.id)
                
        self.state_manager.set_execution_plan(plan)
        self.state_manager.save_state()
        
        # Check if plan is finished now to immediately log episode completion
        if plan.is_finished():
            outcome = "SUCCESS" if plan.is_successful() else "FAILED"
            self.execution_memory.complete_episode(plan.plan_id, outcome)
            
        return result

    def execute_task(self, task, plan) -> Any:
        # Check if task matches a verification task
        if task.type in (TaskType.VERIFY_BUILD, TaskType.RUN_TEST, TaskType.VERIFY_TESTS, TaskType.VERIFY_LINT):
            # Resolve affected files
            affected = [t.target_symbol for t in plan.tasks if t.type in (TaskType.MODIFY_SYMBOL, TaskType.CREATE_SYMBOL)]
            affected_files = []
            for a in affected:
                if not a:
                    continue
                handles = self.verification_engine.resolver.resolve(a)
                if handles:
                    affected_files.extend(list(set(h.file_path for h in handles if h.file_path)))
                else:
                    affected_files.append(a)
            
            stages = []
            if task.type == TaskType.VERIFY_BUILD:
                stages = ["syntax", "build"]
            elif task.type in (TaskType.RUN_TEST, TaskType.VERIFY_TESTS):
                stages = ["syntax", "build", "tests"]
            elif task.type == TaskType.VERIFY_LINT:
                stages = ["lint"]
            else:
                stages = ["syntax", "build", "tests"]
                
            v_plan = VerificationPlan(
                stages=stages,
                test_filter=task.target_symbol if task.type in (TaskType.RUN_TEST, TaskType.VERIFY_TESTS) else None,
                affected_files=list(set(affected_files))
            )
            return self.verification_engine.verify(v_plan)
            
        elif task.type in (TaskType.MODIFY_SYMBOL, TaskType.CREATE_SYMBOL, TaskType.DELETE_SYMBOL, TaskType.REPAIR_IMPORTS, TaskType.REPAIR_COMPILATION, TaskType.REPAIR_SYMBOL, TaskType.REPAIR_FAILURE):
            args = {
                "symbol": task.target_symbol,
                "goal": task.description or plan.goal,
                "path": task.payload.get("file_path"),
                "operation": task.type.value
            }
            return self.executor.dispatch("modify_symbol", args)
            
        elif task.type == TaskType.COMMIT_TRANSACTION:
            return self.executor.dispatch("git_commit", {"message": f"Complete task DAG: {plan.goal}"})
            
        elif task.type == TaskType.VERIFY_CHANGES:
            return self.executor.dispatch("git_diff", {})
            
        else:
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
