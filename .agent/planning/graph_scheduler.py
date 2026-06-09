# planning/graph_scheduler.py

from typing import List, Set, Dict, Any, Optional
from planning.execution_plan import ExecutionPlan
from planning.task_node import TaskNode
from planning.task_status import TaskStatus

class GraphScheduler:
    def __init__(self, plan: ExecutionPlan):
        self.plan = plan

    def next_tasks(self) -> List[TaskNode]:
        """
        Returns a list of runnable tasks that have no outstanding dependencies,
        ensuring that no two running/scheduled tasks edit/target the same file path concurrently.
        """
        if self.plan.is_finished():
            return []

        # Find all currently running tasks
        running_tasks = [t for t in self.plan.tasks if t.status == TaskStatus.RUNNING]
        
        # Gather all file paths currently locked (being written to by running tasks)
        locked_files = set()
        for rt in running_tasks:
            file_path = rt.payload.get("file_path") or rt.file_id
            if file_path:
                locked_files.add(file_path)

        # Get candidates: pending and all dependencies completed
        candidates = []
        for task in self.plan.tasks:
            if task.status != TaskStatus.PENDING:
                continue

            # Check if dependencies are all COMPLETED
            deps_completed = True
            for dep_id in task.dependencies:
                dep_node = self.plan.find_task(dep_id)
                if not dep_node or dep_node.status != TaskStatus.COMPLETED:
                    deps_completed = False
                    break

            if deps_completed:
                candidates.append(task)

        # Apply mutual exclusion scheduling on file paths
        runnable = []
        for task in candidates:
            file_path = task.payload.get("file_path") or task.file_id
            
            if file_path:
                if file_path in locked_files:
                    # File is locked by a running or already scheduled task in this batch
                    continue
                # Lock the file for this batch
                locked_files.add(file_path)
                
            runnable.append(task)

        return runnable

    def mark_started(self, task_id: str):
        task = self.plan.find_task(task_id)
        if task:
            task.status = TaskStatus.RUNNING

    def mark_completed(self, task_id: str):
        self.plan.mark_completed(task_id)

    def mark_failed(self, task_id: str):
        self.plan.mark_failed(task_id)

    def can_retry(self, task_id: str) -> bool:
        task = self.plan.find_task(task_id)
        if task:
            return task.retries < task.max_retries
        return False

    def increment_retries(self, task_id: str):
        task = self.plan.find_task(task_id)
        if task:
            task.retries += 1
            task.status = TaskStatus.PENDING
