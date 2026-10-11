# validation/safety_policy.py
from enum import Enum
from validation.validation_result import ValidationResult, ValidationStatus

class SafetyDecision(Enum):
    APPLY = "apply"
    REQUIRE_CONFIRMATION = "require_confirmation"
    BLOCK = "block"
    ROLLBACK = "rollback"

class SafetyPolicy:
    @staticmethod
    def decide(result: ValidationResult) -> SafetyDecision:
        if result.status in (ValidationStatus.FAILED, ValidationStatus.ERROR):
            return SafetyDecision.ROLLBACK
            
        if result.confidence > 0.9:
            return SafetyDecision.APPLY
        elif result.confidence > 0.55:
            return SafetyDecision.REQUIRE_CONFIRMATION
        else:
            return SafetyDecision.BLOCK
