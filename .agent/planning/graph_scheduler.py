# planning/graph_scheduler.py

from typing import List, Set, Dict, Any, Optional
from planning.execution_plan import ExecutionPlan, ExecutionStage
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

    def build_execution_stages(self) -> List[ExecutionStage]:
        """
        Group tasks into sequential execution stages, where tasks within the same
        stage can be executed in parallel (subject to file locking at runtime).
        """
        # Build dependency adjacency list and in-degrees
        in_degree = {}
        adj = {}
        for task in self.plan.tasks:
            in_degree[task.id] = 0
            adj[task.id] = []

        # Populate edges (dependency: dep_id -> task.id)
        for task in self.plan.tasks:
            for dep_id in task.dependencies:
                if dep_id in in_degree:
                    adj[dep_id].append(task.id)
                    in_degree[task.id] += 1

        # Multi-source BFS topological sort
        stages = []
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        stage_counter = 1

        while queue:
            # Sort task IDs for deterministic stage order
            queue.sort()
            stage_tasks = list(queue)
            stages.append(ExecutionStage(
                stage_id=f"stage_{stage_counter}",
                parallel_tasks=stage_tasks
            ))
            stage_counter += 1

            next_queue = []
            for u in stage_tasks:
                for v in adj[u]:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        next_queue.append(v)
            queue = next_queue

        # Fallback for remaining unvisited nodes (if cycle exists)
        visited = set()
        for s in stages:
            visited.update(s.parallel_tasks)
            
        remaining = [t.id for t in self.plan.tasks if t.id not in visited]
        if remaining:
            remaining.sort()
            stages.append(ExecutionStage(
                stage_id=f"stage_{stage_counter}",
                parallel_tasks=remaining
            ))

        return stages

    def insert_new_tasks(self, new_tasks: List[TaskNode]):
        """
        Inserts new tasks into the ExecutionPlan, updates the underlying TaskGraph,
        and regenerates the topological execution stages.
        """
        for nt in new_tasks:
            if not self.plan.find_task(nt.id):
                self.plan.tasks.append(nt)
                if self.plan.graph:
                    self.plan.graph.add_node(nt)
                    for dep in nt.dependencies:
                        self.plan.graph.add_edge(dep, nt.id)
                        
        # Rebuild stages topologically
        self.plan.stages = self.build_execution_stages()
