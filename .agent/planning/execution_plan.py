# planning/execution_plan.py
#
# ExecutionPlan dataclass holding compiled TaskNodes DAG.

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import uuid4
from planning.task_node import TaskNode
from planning.task_types import TaskType
from planning.task_status import TaskStatus
from planning.planning_strategy import PlanningStrategy

@dataclass
class ExecutionPlan:
    goal: str
    plan_id: str = field(default_factory=lambda: str(uuid4()))
    strategy: PlanningStrategy = PlanningStrategy.FEATURE
    tasks: List[TaskNode] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def find_task(self, task_id: str) -> Optional[TaskNode]:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_runnable_tasks(self) -> List[TaskNode]:
        """
        Returns all tasks that are PENDING and have all of their dependencies COMPLETED.
        """
        runnable = []
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            
            # Check if all dependencies are COMPLETED
            deps_completed = True
            for dep_id in task.dependencies:
                dep_node = self.find_task(dep_id)
                if not dep_node or dep_node.status != TaskStatus.COMPLETED:
                    deps_completed = False
                    break
            
            if deps_completed:
                runnable.append(task)
        return runnable

    def mark_completed(self, task_id: str):
        task = self.find_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED

    def mark_failed(self, task_id: str):
        """
        Marks a task as FAILED and propagates the failure to mark downstream dependent tasks as SKIPPED.
        """
        task = self.find_task(task_id)
        if not task:
            return
        
        task.status = TaskStatus.FAILED
        self._propagate_skip(task_id)

    def _propagate_skip(self, failed_task_id: str):
        """
        Transitively marks all tasks that depend on the failed task (or on skipped tasks) as SKIPPED.
        """
        changed = True
        skipped_set = {failed_task_id}
        
        while changed:
            changed = False
            for task in self.tasks:
                if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    # Check if it depends on any skipped or failed task
                    has_failed_dep = False
                    for dep_id in task.dependencies:
                        dep_node = self.find_task(dep_id)
                        if dep_id in skipped_set or (dep_node and dep_node.status in (TaskStatus.FAILED, TaskStatus.SKIPPED)):
                            has_failed_dep = True
                            break
                    
                    if has_failed_dep:
                        task.status = TaskStatus.SKIPPED
                        skipped_set.add(task.id)
                        changed = True

    def is_finished(self) -> bool:
        """
        Returns True if there are no PENDING or RUNNING tasks.
        """
        for task in self.tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return False
        return True

    def is_successful(self) -> bool:
        """
        Returns True if the finished plan has no FAILED tasks.
        (SKIPPED is okay if it's expected, but usually we want no FAILED status).
        """
        for task in self.tasks:
            if task.status == TaskStatus.FAILED:
                return False
        return True

    def has_cycles(self) -> bool:
        """
        Returns True if the task dependency graph contains a cycle.
        """
        visited = {}  # id -> state: 0=unvisited, 1=visiting, 2=visited
        for task in self.tasks:
            visited[task.id] = 0
            
        def dfs(task_id: str) -> bool:
            if visited.get(task_id) == 1:
                return True  # Found cycle
            if visited.get(task_id) == 2:
                return False
                
            visited[task_id] = 1
            task = self.find_task(task_id)
            if task:
                for dep_id in task.dependencies:
                    if dfs(dep_id):
                        return True
            visited[task_id] = 2
            return False

        for task in self.tasks:
            if visited[task.id] == 0:
                if dfs(task.id):
                    return True
        return False

    # =========================================================
    # SERIALIZATION
    # =========================================================

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "strategy": self.strategy.value,
            "tasks": [
                {
                    "id": t.id,
                    "type": t.type.value,
                    "target_symbol": t.target_symbol,
                    "dependencies": t.dependencies,
                    "description": t.description,
                    "status": t.status.value,
                    "retries": t.retries,
                    "max_retries": t.max_retries,
                    "payload": t.payload,
                    "symbol_id": t.symbol_id,
                    "symbol_name": t.symbol_name,
                    "file_id": t.file_id
                }
                for t in self.tasks
            ],
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionPlan":
        created_at_str = data.get("created_at")
        try:
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now()
        except Exception:
            created_at = datetime.now()

        try:
            strategy = PlanningStrategy(data.get("strategy", "feature"))
        except ValueError:
            strategy = PlanningStrategy.FEATURE
        
        tasks = []
        for t_dict in data.get("tasks", []):
            tasks.append(TaskNode(
                id=t_dict["id"],
                type=TaskType(t_dict["type"]),
                target_symbol=t_dict.get("target_symbol"),
                dependencies=t_dict.get("dependencies", []),
                description=t_dict.get("description", ""),
                status=TaskStatus(t_dict.get("status", "PENDING")),
                retries=t_dict.get("retries", 0),
                max_retries=t_dict.get("max_retries", 3),
                payload=t_dict.get("payload", {}),
                symbol_id=t_dict.get("symbol_id"),
                symbol_name=t_dict.get("symbol_name"),
                file_id=t_dict.get("file_id")
            ))
        plan = cls(
            goal=data["goal"],
            plan_id=data.get("plan_id", str(uuid4())),
            strategy=strategy,
            tasks=tasks,
            created_at=created_at
        )
        return plan

    # =========================================================
    # PERSISTENCE
    # =========================================================

    def save(self, path: str):
        """Persist the execution plan to a JSON file on disk."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "ExecutionPlan":
        """Load an execution plan from a JSON file on disk."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
