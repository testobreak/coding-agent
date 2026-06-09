# execution/verification_result.py
#
# Dataclasses representing structured verification results, sub-results, issues, and status.

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional

class VerificationStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ERROR = "ERROR"

@dataclass
class BuildResult:
    success: bool
    errors: List[str] = field(default_factory=list)
    stdout: str = ""

@dataclass
class LintResult:
    success: bool
    issues: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class TestResult:
    success: bool
    failed_tests: List[str] = field(default_factory=list)
    evidence: str = ""

@dataclass
class VerificationIssue:
    type: str  # e.g., "COMPILATION_ERROR", "TEST_FAILURE", "SYNTAX_ERROR", "LINT_ERROR", "POLICY_VIOLATION"
    file: str
    line: Optional[int]
    message: str
    symbol: Optional[str] = None
    severity: str = "HIGH"  # HIGH, MEDIUM, LOW
    category: str = "UNKNOWN_ERROR"  # populated by FailureClassifier

@dataclass
class Evidence:
    name: str
    content: str
    timestamp: str

# Legacy Diagnostic model kept for backward compatibility
@dataclass
class Diagnostic:
    type: str          # e.g., "compile_error", "test_failure", "syntax_error", "lint_error"
    symbol: Optional[str] = None
    file_path: str = ""
    line: Optional[int] = None
    message: str = ""

@dataclass
class VerificationResult:
    status: VerificationStatus
    build_result: BuildResult
    lint_result: LintResult
    test_result: TestResult
    issues: List[VerificationIssue] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)

    # =====================================================
    # BACKWARD COMPATIBILITY PROPERTIES
    # =====================================================
    @property
    def success(self) -> bool:
        return self.status == VerificationStatus.SUCCESS

    @property
    def build_passed(self) -> bool:
        return self.build_result.success

    @property
    def tests_passed(self) -> bool:
        return self.test_result.success

    @property
    def lint_passed(self) -> bool:
        return self.lint_result.success

    @property
    def diagnostics(self) -> List[Diagnostic]:
        legacy_diags = []
        for issue in self.issues:
            # Map type string to legacy type string
            legacy_type = "compile_error"
            if issue.type == "TEST_FAILURE":
                legacy_type = "test_failure"
            elif issue.type == "SYNTAX_ERROR":
                legacy_type = "syntax_error"
            elif issue.type == "LINT_ERROR":
                legacy_type = "lint_error"
                
            legacy_diags.append(Diagnostic(
                type=legacy_type,
                file_path=issue.file,
                line=issue.line,
                message=issue.message,
                symbol=issue.symbol
            ))
        return legacy_diags

    def __getitem__(self, key):
        if key == "success":
            return self.success
        if key == "error":
            return "; ".join(i.message for i in self.issues) if self.issues else "Verification failed"
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

@dataclass
class VerificationPlan:
    stages: List[str]  # e.g., ["syntax", "build", "tests", "lint"]
    test_filter: Optional[str] = None
    affected_files: List[str] = field(default_factory=list)
