# validation/validation_engine.py
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from validation.capability_registry import CapabilityRegistry, CapabilityStatus
from validation.workspace_detector import WorkspaceDetector, WorkspaceType
from validation.validation_planner import ValidationPlanner, ValidationPlan
from validation.validation_result import ValidationResult, ValidationStatus
from validation.confidence_engine import ConfidenceEngine
from validation.safety_policy import SafetyPolicy, SafetyDecision

class ValidationEngine:
    def __init__(self, repo_root=None, file_manager=None, capabilities=None, validator=None, compile_validator=None, test_runner=None):
        self.repo_root = Path(repo_root) if repo_root else Path(".")
        self.file_manager = file_manager
        self.capabilities = capabilities or CapabilityRegistry(self.repo_root)
        self.planner = ValidationPlanner(self.capabilities)
        self.validator = validator
        self.compile_validator = compile_validator
        self.test_runner = test_runner

    def validate(
        self,
        affected_files: List[str],
        strategy: Any = None,
        is_surgical_edit: bool = True,
        retrieval_confidence: float = 0.8,
        lines_changed: int = 1
    ) -> ValidationResult:
        """
        Safety inference engine: plans validations, runs checks, computes confidence,
        and evaluates safety decisions.
        """
        # Determine workspace type
        w_type = WorkspaceDetector.detect(self.repo_root)

        # Plan validation stages
        plan = self.planner.plan_validation(affected_files, w_type, strategy)

        executed_checks = []
        skipped_checks = []
        errors = []
        status = ValidationStatus.PASSED

        if plan.skip_reason:
            status = ValidationStatus.SKIPPED
            skipped_checks = plan.stages
            errors = [plan.skip_reason]
        else:
            # 1. Syntax Check
            if "syntax" in plan.stages:
                if self.validator:
                    for f in affected_files:
                        resolved = self.file_manager.resolve_path(f) if self.file_manager else str(self.repo_root / f)
                        try:
                            self.validator.validate_file_syntax(resolved)
                            executed_checks.append("syntax")
                        except Exception as e:
                            status = ValidationStatus.FAILED
                            executed_checks.append("syntax")
                            errors.append(f"Syntax validation failed for {f}: {e}")
                else:
                    skipped_checks.append("syntax")
            else:
                skipped_checks.append("syntax")

            # 2. Compile Check
            if "compile" in plan.stages or "build" in plan.stages:
                if status == ValidationStatus.PASSED and self.compile_validator:
                    from core.validation_mode import ValidationState
                    for f in affected_files:
                        resolved = self.file_manager.resolve_path(f) if self.file_manager else str(self.repo_root / f)
                        try:
                            v_state = self.compile_validator.validate(resolved)
                            if v_state == ValidationState.FAILED:
                                status = ValidationStatus.FAILED
                                executed_checks.append("compile")
                                errors.append("Compilation validation failed.")
                            elif v_state in (ValidationState.UNAVAILABLE, ValidationState.SKIPPED):
                                skipped_checks.append("compile")
                            else:
                                executed_checks.append("compile")
                        except Exception as e:
                            status = ValidationStatus.FAILED
                            executed_checks.append("compile")
                            errors.append(f"Compile check exception: {e}")
                else:
                    skipped_checks.append("compile")
            else:
                skipped_checks.append("compile")

            # 3. Test Check
            if "tests" in plan.stages:
                if status == ValidationStatus.PASSED and self.test_runner:
                    # Run backend tests
                    try:
                        test_result = self.test_runner.run_backend_tests(
                            touched_files=affected_files,
                        )
                    except Exception as e:
                        test_result = {"success": False, "error": str(e)}

                    if test_result.get("error") and "Command not found" in test_result.get("error", ""):
                        skipped_checks.append("tests")
                    elif not test_result.get("success", False):
                        status = ValidationStatus.FAILED
                        executed_checks.append("tests")
                        failures = test_result.get("failures", [])
                        failure_summary = "; ".join([f"{f.get('error_type')}: {f.get('message')}" for f in failures[:3]]) or test_result.get("error") or "Test suite execution failed"
                        errors.append(failure_summary)
                    else:
                        executed_checks.append("tests")
                else:
                    skipped_checks.append("tests")
            else:
                skipped_checks.append("tests")

        # Determine overall status (PARTIAL if some executed and some skipped, none failed)
        if status == ValidationStatus.PASSED:
            if skipped_checks and executed_checks:
                status = ValidationStatus.PARTIAL
            elif skipped_checks and not executed_checks:
                status = ValidationStatus.SKIPPED

        # Compute confidence score
        confidence = ConfidenceEngine.compute_confidence(
            validation_status=status,
            is_surgical_edit=is_surgical_edit,
            retrieval_confidence=retrieval_confidence,
            lines_changed=lines_changed
        )

        return ValidationResult(
            status=status,
            executed_checks=executed_checks,
            skipped_checks=skipped_checks,
            failed_checks=errors if status in (ValidationStatus.FAILED, ValidationStatus.ERROR) else [],
            logs=errors,
            confidence=confidence
        )
