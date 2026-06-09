# execution/quality_gate.py
#
# QualityGateEvaluator defines policies to check whether a verification run satisfies
# all acceptance criteria.

from typing import List, Tuple
from execution.verification_result import VerificationResult, VerificationStatus

class QualityGateEvaluator:
    def evaluate(self, result: VerificationResult) -> Tuple[bool, List[str]]:
        """
        Evaluates the verification result.
        Returns a tuple: (passed: bool, failed_policies: List[str]).
        """
        failed_policies = []
        
        # 1. Build must pass
        if not result.build_passed:
            failed_policies.append("Build / compilation check failed.")
            
        # 2. Tests must pass
        if not result.tests_passed:
            failed_policies.append("Test suite run failed.")
            
        # 3. Lint must pass
        if not result.lint_passed:
            failed_policies.append("Static analysis / lint verification failed.")
            
        # 4. No high-severity issues
        high_severity_issues = [i for i in result.issues if i.severity == "HIGH"]
        if high_severity_issues:
            failed_policies.append(f"Found {len(high_severity_issues)} critical or high-severity issues.")
            
        passed = len(failed_policies) == 0
        return passed, failed_policies
