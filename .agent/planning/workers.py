# planning/workers.py

from typing import Any, Dict
from planning.task_node import TaskNode
from planning.task_types import TaskType
from execution.verification_result import VerificationPlan, VerificationResult

class BaseWorker:
    def __init__(self, executor, verification_engine):
        self.executor = executor
        self.verification_engine = verification_engine

    def execute(self, task: TaskNode, plan) -> Any:
        raise NotImplementedError("Subclasses must implement execute")

class RetrievalWorker(BaseWorker):
    def execute(self, task: TaskNode, plan) -> Any:
        # Resolves target symbols and searches context
        args = {
            "symbol": task.target_symbol,
            "goal": task.description or plan.goal,
            "path": task.payload.get("file_path"),
            "operation": task.type.value
        }
        return self.executor.dispatch("retrieve_symbol", args)

class AnalysisWorker(BaseWorker):
    def execute(self, task: TaskNode, plan) -> Any:
        # Runs analysis
        args = {
            "symbol": task.target_symbol,
            "goal": task.description or plan.goal,
            "path": task.payload.get("file_path"),
            "operation": task.type.value
        }
        return self.executor.dispatch("analyze_symbol", args)

class EditWorker(BaseWorker):
    def execute(self, task: TaskNode, plan) -> Any:
        # Dispatches modify/create/delete/rename symbol operations
        args = {
            "symbol": task.target_symbol,
            "goal": task.description or plan.goal,
            "path": task.payload.get("file_path"),
            "operation": task.type.value
        }
        return self.executor.dispatch("modify_symbol", args)

class ValidationWorker(BaseWorker):
    def execute(self, task: TaskNode, plan) -> Any:
        # Dispatches verification runs (syntax, compile, tests, lint)
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

class RepairWorker(BaseWorker):
    def execute(self, task: TaskNode, plan) -> Any:
        # Coordinates repair patching
        args = {
            "symbol": task.target_symbol,
            "goal": task.description or plan.goal,
            "path": task.payload.get("file_path"),
            "operation": task.type.value
        }
        return self.executor.dispatch("modify_symbol", args)
