# planning/task_node.py
#
# TaskNode dataclass representing a node in the execution DAG.

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from planning.task_types import TaskType
from planning.task_status import TaskStatus

@dataclass
class TaskNode:
    id: str
    type: TaskType
    target_symbol: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    max_retries: int = 3
    payload: dict = field(default_factory=dict)
    
    # Precise symbol-level metadata
    symbol_id: Optional[str] = None
    symbol_name: Optional[str] = None
    file_id: Optional[str] = None
    repository_id: Optional[str] = None

    # New Phase 13 fields
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    symbol_refs: List[Any] = field(default_factory=list)  # List of SymbolRef objects

    @property
    def task_type(self) -> TaskType:
        return self.type
    
    @task_type.setter
    def task_type(self, val: TaskType):
        self.type = val

    @property
    def depends_on(self) -> List[str]:
        # Backward compatibility alias
        return self.dependencies

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "target_symbol": self.target_symbol,
            "dependencies": self.dependencies,
            "description": self.description,
            "status": self.status.value,
            "retries": self.retries,
            "max_retries": self.max_retries,
            "payload": self.payload,
            "symbol_id": self.symbol_id,
            "symbol_name": self.symbol_name,
            "file_id": self.file_id,
            "repository_id": self.repository_id,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "symbol_refs": [ref.to_dict() if hasattr(ref, "to_dict") else ref for ref in self.symbol_refs]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskNode":
        from planning.task_graph import SymbolRef
        
        # Parse symbol_refs
        s_refs = []
        for ref_data in data.get("symbol_refs", []):
            s_refs.append(SymbolRef.from_dict(ref_data))

        return cls(
            id=data["id"],
            type=TaskType(data["type"]),
            target_symbol=data.get("target_symbol"),
            dependencies=data.get("dependencies", []),
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "PENDING")),
            retries=data.get("retries", 0),
            max_retries=data.get("max_retries", 3),
            payload=data.get("payload", {}),
            symbol_id=data.get("symbol_id"),
            symbol_name=data.get("symbol_name"),
            file_id=data.get("file_id"),
            repository_id=data.get("repository_id"),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            symbol_refs=s_refs
        )
