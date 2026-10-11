# validation/confidence_engine.py
from validation.validation_result import ValidationStatus

class ConfidenceEngine:
    @staticmethod
    def calculate_validation_score(status: ValidationStatus) -> float:
        if status == ValidationStatus.PASSED:
            return 1.0
        elif status == ValidationStatus.PARTIAL:
            return 0.6
        elif status == ValidationStatus.SKIPPED:
            return 0.15
        elif status in (ValidationStatus.FAILED, ValidationStatus.ERROR):
            return 0.0
        return 0.0

    @staticmethod
    def calculate_locality_score(is_surgical_edit: bool = True) -> float:
        return 1.0 if is_surgical_edit else 0.3

    @staticmethod
    def calculate_patch_size_score(lines_changed: int) -> float:
        return 1.0 if lines_changed < 15 else 0.3

    @classmethod
    def compute_confidence(
        cls,
        validation_status: ValidationStatus,
        is_surgical_edit: bool = True,
        retrieval_confidence: float = 0.8,
        lines_changed: int = 1
    ) -> float:
        validation_score = cls.calculate_validation_score(validation_status)
        edit_locality_score = cls.calculate_locality_score(is_surgical_edit)
        patch_size_score = cls.calculate_patch_size_score(lines_changed)

        confidence = (
            validation_score * 0.55 +
            edit_locality_score * 0.20 +
            patch_size_score * 0.15 +
            retrieval_confidence * 0.10
        )
        return round(confidence, 2)
