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
        Classifies issues inside VerificationResult and coordinates repair task planning,
        generating a structured Repair Subgraph DAG (Diagnose -> Retrieve -> Patch -> Revalidate).
        """
        self.increment_attempts(key)
        
        # 1. Classify all issues to enrich diagnostics context
        for issue in result.issues:
            issue.category = self.classifier.classify(issue.type, issue.message)
            
        # 2. Plan flat repair tasks using the planner
        flat_repairs = self.planner.plan_repairs(result, goal)
        if not flat_repairs:
            return []
            
        from planning.task_types import TaskType
        from planning.task_status import TaskStatus
        
        subgraph_nodes = []
        for idx, rep in enumerate(flat_repairs):
            diag_id = f"diag_{key}_{idx}"
            
            # 1. Diagnose Task
            diagnose_node = TaskNode(
                id=f"diagnose_{diag_id}",
                type=TaskType.ANALYZE_FAILURE,
                description=f"Diagnose failure: {rep.description}",
                dependencies=[],
                status=TaskStatus.PENDING,
                payload=rep.payload,
                symbol_id=rep.symbol_id,
                symbol_name=rep.symbol_name or rep.target_symbol,
                file_id=rep.file_id or rep.payload.get("file_path")
            )
            diagnose_node.target_symbol = rep.target_symbol
            
            # 2. Retrieve Context Task
            retrieve_node = TaskNode(
                id=f"retrieve_context_{diag_id}",
                type=TaskType.RETRIEVE_CONTEXT,
                description=f"Retrieve repair context for {rep.target_symbol or 'failure'}",
                dependencies=[diagnose_node.id],
                status=TaskStatus.PENDING,
                payload=rep.payload,
                symbol_id=rep.symbol_id,
                symbol_name=rep.symbol_name or rep.target_symbol,
                file_id=rep.file_id or rep.payload.get("file_path")
            )
            retrieve_node.target_symbol = rep.target_symbol
            
            # 3. Patch/Repair Task (maps to the original planned repair node)
            patch_node = TaskNode(
                id=f"patch_{diag_id}",
                type=rep.type,
                description=rep.description,
                dependencies=[retrieve_node.id],
                status=TaskStatus.PENDING,
                payload=rep.payload,
                symbol_id=rep.symbol_id,
                symbol_name=rep.symbol_name or rep.target_symbol,
                file_id=rep.file_id or rep.payload.get("file_path")
            )
            patch_node.target_symbol = rep.target_symbol
            
            # 4. Revalidate Task
            revalidate_node = TaskNode(
                id=f"revalidate_{diag_id}",
                type=TaskType.VERIFY_BUILD,
                description=f"Revalidate repair patch for {rep.target_symbol or 'failure'}",
                dependencies=[patch_node.id],
                status=TaskStatus.PENDING,
                payload=rep.payload,
                symbol_id=rep.symbol_id,
                symbol_name=rep.symbol_name or rep.target_symbol,
                file_id=rep.file_id or rep.payload.get("file_path")
            )
            revalidate_node.target_symbol = rep.target_symbol
            
            subgraph_nodes.extend([diagnose_node, retrieve_node, patch_node, revalidate_node])
            
        return subgraph_nodes
