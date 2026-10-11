# validation/validation_planner.py
from dataclasses import dataclass, field
from typing import List, Optional, Any
from validation.capability_registry import CapabilityRegistry, CapabilityStatus
from validation.workspace_detector import WorkspaceType

@dataclass
class ValidationPlan:
    fast_checks: List[str]    # e.g. ["syntax"]
    medium_checks: List[str]  # e.g. ["compile"]
    slow_checks: List[str]    # e.g. ["tests"]
    required_tool: Optional[str] = None
    skip_reason: Optional[str] = None

    # Keep compatibility with old VerificationPlan properties if needed
    @property
    def stages(self) -> List[str]:
        return self.fast_checks + self.medium_checks + self.slow_checks

class ValidationPlanner:
    def __init__(self, capabilities: CapabilityRegistry):
        self.capabilities = capabilities

    def plan_validation(
        self,
        affected_files: List[str],
        workspace_type: Any = None,
        strategy: Any = None,
        **kwargs
    ) -> ValidationPlan:
        w_type = workspace_type or kwargs.get("project_type")
        if not w_type:
            w_type = WorkspaceType.UNKNOWN

        if not isinstance(w_type, WorkspaceType):
            w_str = str(getattr(w_type, "value", w_type)).lower()
            if w_str in ("java_maven", "maven"):
                w_type = WorkspaceType.JAVA_MAVEN
            elif w_str in ("java_gradle", "gradle"):
                w_type = WorkspaceType.JAVA_GRADLE
            elif w_str in ("node", "npm"):
                w_type = WorkspaceType.NODE
            elif w_str in ("python", "pytest"):
                w_type = WorkspaceType.PYTHON
            else:
                w_type = WorkspaceType.UNKNOWN

        required_tool = None
        if w_type == WorkspaceType.JAVA_MAVEN:
            required_tool = "maven"
        elif w_type == WorkspaceType.NODE:
            required_tool = "npm"
        elif w_type == WorkspaceType.PYTHON:
            required_tool = "pytest"
        elif w_type == WorkspaceType.JAVA_GRADLE:
            required_tool = "java"

        skip_reason = None
        if required_tool:
            cap = self.capabilities.capabilities.get(required_tool)
            if not cap or cap.status != CapabilityStatus.AVAILABLE:
                skip_reason = f"Required tool '{required_tool}' is missing or broken"

        fast_checks = []
        medium_checks = []
        slow_checks = []

        if strategy is None:
            fast_checks = ["syntax"]
            medium_checks = ["compile"]
            slow_checks = ["tests"]
        else:
            if getattr(strategy, "validate_syntax", True):
                fast_checks.append("syntax")
            if getattr(strategy, "validate_compile", True):
                medium_checks.append("compile")
            if getattr(strategy, "run_tests", True):
                slow_checks.append("tests")

        return ValidationPlan(
            fast_checks=fast_checks,
            medium_checks=medium_checks,
            slow_checks=slow_checks,
            required_tool=required_tool,
            skip_reason=skip_reason
        )
