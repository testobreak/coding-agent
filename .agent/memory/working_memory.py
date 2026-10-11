# memory/working_memory.py

from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class WorkingMemory:
    retrieved_symbols: List[Dict[str, Any]] = field(default_factory=list)
    dependency_neighbors: List[Dict[str, Any]] = field(default_factory=list)
    patch_candidates: List[Dict[str, Any]] = field(default_factory=list)

    touched_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    modification_targets: List[str] = field(default_factory=list)
    active_symbols: List[str] = field(default_factory=list)
    architecture_notes: List[str] = field(default_factory=list)
    pending_executions: List[Dict[str, Any]] = field(default_factory=list)
    current_plan: List[Dict[str, Any]] = field(default_factory=list)
    replans: List[str] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    callers: List[Any] = field(default_factory=list)
    callees: List[Any] = field(default_factory=list)
