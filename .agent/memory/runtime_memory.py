# memory/runtime_memory.py

from dataclasses import (
    dataclass,
    field
)

from typing import Dict, Any


@dataclass
class RuntimeMemory:

    total_iterations: int = 0

    retrieval_count: int = 0

    modification_count: int = 0

    validation_count: int = 0

    repair_count: int = 0

    tool_call_count: int = 0

    tokens_used: int = 0

    runtime_errors: int = 0

    successful_repairs: int = 0

    failed_repairs: int = 0

    execution_time_seconds: float = 0.0

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )
