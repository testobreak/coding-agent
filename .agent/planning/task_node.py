# planning/task_node.py
#
# TaskNode dataclass representing a node in the execution DAG.

from dataclasses import dataclass, field
from planning.task_types import TaskType
from planning.task_status import TaskStatus

@dataclass
class TaskNode:
    id: str
    type: TaskType
    target_symbol: str | None = None
    dependencies: list[str] = field(default_factory=list)
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    max_retries: int = 3
    payload: dict = field(default_factory=dict)
    
    # Precise symbol-level metadata
    symbol_id: str | None = None
    symbol_name: str | None = None
    file_id: str | None = None

    @property
    def depends_on(self) -> list[str]:
        # Backward compatibility alias
        return self.dependencies
