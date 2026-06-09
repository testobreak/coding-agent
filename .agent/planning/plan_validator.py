# planning/plan_validator.py
#
# Plan Validation Layer. Checks plans for consistency, cycles, missing dependencies,
# and target symbol existence before they are sent to the execution engine.

import os
from planning.execution_plan import ExecutionPlan
from planning.task_types import TaskType
from context.symbol_resolver import SymbolResolver

class PlanValidator:
    def __init__(self, db_session=None, repo_root=None):
        self.resolver = SymbolResolver()
        self.db_session = db_session
        self.repo_root = repo_root or "/Users/ashish/Downloads/HRMS"

    def validate(self, plan: ExecutionPlan) -> list[str]:
        errors = []
        
        # 1. Check for cycles
        if plan.has_cycles():
            errors.append("Validation failed: Task dependency cycle detected.")
            
        task_ids = {t.id for t in plan.tasks}
        
        for task in plan.tasks:
            # 2. Check dependencies exist
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    errors.append(f"Validation failed: Task '{task.id}' depends on non-existent task '{dep_id}'.")
                    
            # 3. Check target symbol exists
            if task.type in (TaskType.MODIFY_SYMBOL, TaskType.DELETE_SYMBOL):
                if not task.target_symbol:
                    errors.append(f"Validation failed: Task '{task.id}' ({task.type.value}) requires a target symbol.")
                else:
                    symbol_found = self.target_symbol_exists(task.target_symbol)
                    # If not found, let's check if it's a file path
                    if not symbol_found:
                        file_found = False
                        # If target_symbol has dot, resolve it
                        try:
                            # Try resolving symbol to see if any file exists matching it
                            file_found = os.path.exists(os.path.join(self.repo_root, task.target_symbol))
                        except Exception:
                            pass
                        
                        # Check payload for a fallback path
                        fallback_path = task.payload.get("file_path") or task.payload.get("path")
                        if fallback_path:
                            file_found = os.path.exists(os.path.join(self.repo_root, fallback_path))
                            
                        if not file_found:
                            errors.append(f"Validation failed: Target symbol or file '{task.target_symbol}' could not be resolved.")
                            
            # 4. Check test targets
            if task.type in (TaskType.RUN_TEST, TaskType.UPDATE_TEST):
                if task.target_symbol:
                    test_found = self.tests_resolvable(task.target_symbol)
                    if not test_found:
                        # If a specific test target is named but not resolvable in the db/project, log warning or error
                        # To be safe and avoid blocking compilation if we are adding new tests, we can just warn or log
                        print(f"[PlanValidator] Warning: Test target '{task.target_symbol}' might not exist yet.")
                        
        return errors

    def target_symbol_exists(self, symbol_name: str) -> bool:
        """
        Queries the SymbolResolver to check if the symbol exists.
        """
        try:
            resolved = self.resolver.resolve(symbol_name, session=self.db_session)
            return len(resolved) > 0
        except Exception as e:
            print(f"[PlanValidator] Resolver lookup failed for {symbol_name}: {e}")
            return False

    def tests_resolvable(self, test_name: str) -> bool:
        """
        Checks if a test class or test file exists.
        """
        # Checks if test_name exists as a symbol or file
        if self.target_symbol_exists(test_name):
            return True
        
        # Check if the name looks like a test file
        test_file_variants = [
            test_name,
            f"{test_name}.py",
            f"{test_name}.java",
            f"backend/src/test/java/com/hrms/{test_name.replace('.', '/')}.java",
            f"backend/src/test/java/{test_name.replace('.', '/')}.java"
        ]
        for variant in test_file_variants:
            if os.path.exists(os.path.join(self.repo_root, variant)):
                return True
        return False
