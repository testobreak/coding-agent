# planning/repair_engine.py
#
# RepairEngine acts as the orchestrator for diagnosing and repairing validation errors
# while enforcing retry limits.

from typing import List
from execution.failure_classifier import FailureClassifier
from execution.verification_result import VerificationResult
from planning.repair_planner import RepairPlanner
from planning.task_node import TaskNode

class RepairEngine:
    def __init__(self, llm=None, max_attempts: int = 3):
        self.planner = RepairPlanner(llm=llm)
        self.classifier = FailureClassifier()
        self.max_attempts = max_attempts
        self.attempts_history = {}  # key (plan_id or task_id) -> retry count

    def check_budget(self, key) -> bool:
        """
        Returns True if repair attempts for the given key/plan have not reached max_attempts.
        """
        plan_id = key
        plan_obj = None
        
        # If key is an ExecutionPlan object
        if hasattr(key, "plan_id"):
            plan_id = key.plan_id
            plan_obj = key
            
        # 1. Check in-memory history first
        if self.attempts_history.get(plan_id, 0) >= self.max_attempts:
            return False
            
        # 2. Check the number of repair tasks in the plan itself
        if plan_obj and hasattr(plan_obj, "tasks"):
            from planning.task_types import TaskType
            repair_types = {
                TaskType.REPAIR_IMPORTS,
                TaskType.REPAIR_COMPILATION,
                TaskType.REPAIR_SYMBOL,
                TaskType.REPAIR_FAILURE
            }
            repair_count = sum(
                1 for t in plan_obj.tasks 
                if t.type in repair_types or (t.type and t.type.value in {rt.value for rt in repair_types})
            )
            if repair_count >= self.max_attempts:
                return False
                
        return True

    def increment_attempts(self, key: str):
        """
        Increments the repair attempt counter for the given key.
        """
        self.attempts_history[key] = self.attempts_history.get(key, 0) + 1

    def get_attempts(self, key: str) -> int:
        return self.attempts_history.get(key, 0)

    def repair(self, result: VerificationResult, goal: str, key: str = "unknown") -> List[TaskNode]:
        """
        Classifies issues inside VerificationResult and coordinates repair task planning.
        """
        self.increment_attempts(key)
        
        # 1. Classify all issues to enrich diagnostics context
        for issue in result.issues:
            issue.category = self.classifier.classify(issue.type, issue.message)
            
        # 2. Plan repair tasks using the planner
        return self.planner.plan_repairs(result, goal)
