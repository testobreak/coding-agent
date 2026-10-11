# validation/validation_result.py
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Any

class ValidationStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    PARTIAL = "partial"

@dataclass
class ValidationResult:
    status: ValidationStatus
    executed_checks: List[str] = field(default_factory=list)
    skipped_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    confidence: float = 0.0
    errors: List[str] = field(default_factory=list)
    output: str = ""
    reason: Any = None
    stage_results: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.errors and not self.logs:
            self.logs = list(self.errors)
        if self.logs and not self.errors:
            self.errors = list(self.logs)
        if self.logs and not self.output:
            self.output = "; ".join(self.logs)

    # Compatibility mapping for verification engine results
    @property
    def success(self) -> bool:
        return self.status in (ValidationStatus.PASSED, ValidationStatus.PARTIAL)
