# memory/execution_history.py

from dataclasses import dataclass, field

from typing import Dict, Any

from datetime import datetime


@dataclass
class ExecutionRecord:

    action_id: str

    tool: str

    status: str

    started_at: str = field(
        default_factory=lambda:
        datetime.utcnow().isoformat()
    )

    completed_at: str = ""

    duration_seconds: float = 0.0

    retries: int = 0

    success: bool = False

    input_data: Dict[str, Any] = field(
        default_factory=dict
    )

    output_data: Dict[str, Any] = field(
        default_factory=dict
    )

    error: str = ""
