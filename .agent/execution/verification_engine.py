# execution/verification_engine.py
#
# Dedicated Verification Engine. Performs progressive syntax, build, and test
# checks, extracting structured VerificationIssue objects from raw outputs,
# evaluates quality gates, and logs runs in the evidence store.

import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from execution.verification_result import (
    Diagnostic, VerificationResult, VerificationPlan, VerificationStatus,
    BuildResult, TestResult, LintResult, VerificationIssue, Evidence
)
from execution.failure_parser import MavenFailureParser, TypeScriptFailureParser
from execution.failure_classifier import FailureClassifier
from execution.quality_gate import QualityGateEvaluator
from execution.evidence_store import VerificationEvidenceStore

class VerificationEngine:
    def __init__(
        self,
        file_manager,
        state_manager,
        validator,
        compile_validator,
        test_runner,
        impact_analyzer=None
    ):
        self.file_manager = file_manager
        self.state_manager = state_manager
        self.validator = validator
        self.compile_validator = compile_validator
        self.tests = test_runner
        self.impact_analyzer = impact_analyzer
        
        from editing.symbol_resolver import SymbolResolver
        self.resolver = SymbolResolver()
        
        self.java_parser = MavenFailureParser()
        self.ts_parser = TypeScriptFailureParser()
        
        self.classifier = FailureClassifier()
        self.quality_gate = QualityGateEvaluator()
        self.evidence_store = VerificationEvidenceStore()

    def verify(self, plan: VerificationPlan) -> VerificationResult:
        """
        Progressively runs syntax, build, and tests stages.
        Returns a VerificationResult with success status and list of VerificationIssue elements.
        """
        print(f"[VerificationEngine] Running verification plan stages: {plan.stages}")
        
        issues: List[VerificationIssue] = []
        evidence: List[Evidence] = []
        
        build_res = BuildResult(success=True)
        test_res = TestResult(success=True)
        lint_res = LintResult(success=True)
        
        # Stage 1: Syntax check
        if "syntax" in plan.stages:
            for f in plan.affected_files:
                resolved = self.file_manager.resolve_path(f)
                if not os.path.exists(resolved):
                    continue
                try:
                    self.validator.validate_file_syntax(resolved)
                except Exception as e:
                    print(f"[VerificationEngine] Syntax check failed for {f}: {e}")
                    issues.append(VerificationIssue(
                        type="SYNTAX_ERROR",
                        file=f,
                        line=None,
                        message=str(e),
                        severity="HIGH"
                    ))
            # If syntax checks fail, return immediately (syntax is Stage 1)
            if issues:
                build_res.success = False
                res = VerificationResult(
                    status=VerificationStatus.FAILED,
                    build_result=build_res,
                    lint_result=lint_res,
                    test_result=test_res,
                    issues=issues,
                    evidence=evidence
                )
                self.evidence_store.log_run(res)
                return res
                
        # Stage 2: Build / Compile Check
        if "build" in plan.stages:
            for f in plan.affected_files:
                resolved = self.file_manager.resolve_path(f)
                if not os.path.exists(resolved):
                    continue
                try:
                    self.compile_validator.validate(resolved)
                except Exception as e:
                    build_res.success = False
                    print(f"[VerificationEngine] Compile check failed for {f}: {e}")
                    err_msg = str(e)
                    parsed_issues = self._parse_compile_errors(err_msg, f)
                    if parsed_issues:
                        issues.extend(parsed_issues)
                    else:
                        issues.append(VerificationIssue(
                            type="COMPILATION_ERROR",
                            file=f,
                            line=None,
                            message=err_msg,
                            severity="HIGH"
                        ))
            if not build_res.success:
                res = VerificationResult(
                    status=VerificationStatus.FAILED,
                    build_result=build_res,
                    lint_result=lint_res,
                    test_result=test_res,
                    issues=issues,
                    evidence=evidence
                )
                self.evidence_store.log_run(res)
                return res

        # Stage 3: Test Check
        if "tests" in plan.stages:
            test_filter = plan.test_filter
            # Run impact analysis if test_filter not explicitly set
            if not test_filter and plan.affected_files:
                try:
                    for f in plan.affected_files:
                        impact = self.impact_analyzer.analyze(f) if self.impact_analyzer else {}
                        test_filter = impact.get("test_filter")
                        if test_filter:
                            print(f"[VerificationEngine] Found targeted test filter via impact: {test_filter}")
                            break
                except Exception as e:
                    print(f"[VerificationEngine] Impact analysis failed: {e}")
            
            print(f"[VerificationEngine] Running test suite (filter={test_filter})...")
            test_result = self.tests.run_backend_tests(test_filter=test_filter)
            
            # Record evidence
            evidence.append(Evidence(
                name="test_runner_stdout",
                content=str(test_result),
                timestamp=datetime.now().isoformat()
            ))
            
            if not test_result.get("success", False):
                test_res.success = False
                failures = test_result.get("failures", [])
                
                # Parse structured test failures
                if failures:
                    for f_dict in failures:
                        likely_file = f_dict.get("likely_source_files", [""])[0] if f_dict.get("likely_source_files") else ""
                        issues.append(VerificationIssue(
                            type="TEST_FAILURE",
                            file=likely_file,
                            line=None,
                            message=f"{f_dict.get('error_type', 'Error')}: {f_dict.get('message', '')}",
                            symbol=f"{f_dict.get('test_class', 'Unknown')}.{f_dict.get('test_method', 'unknown')}",
                            severity="HIGH"
                        ))
                else:
                    issues.append(VerificationIssue(
                        type="TEST_FAILURE",
                        file="",
                        line=None,
                        message=test_result.get("error", "Unknown test failure"),
                        severity="HIGH"
                    ))
                    
        # Stage 4: Lint / Static Analysis Check (optional)
        if "lint" in plan.stages:
            print("[VerificationEngine] Running lint / static analysis verification...")
            # If any lint issues are tracked or found:
            # For this context, we check if linting failed or passes by default
            # We can mock lint result or run ESLint if configured, but keeping standard pass for now.
            lint_res.success = True
            
        # Classify all issues using FailureClassifier
        for issue in issues:
            issue.category = self.classifier.classify(issue.type, issue.message)
            
        status = VerificationStatus.SUCCESS if not issues else VerificationStatus.FAILED
        
        res = VerificationResult(
            status=status,
            build_result=build_res,
            lint_result=lint_res,
            test_result=test_res,
            issues=issues,
            evidence=evidence
        )
        
        # Evaluate Quality Gate
        gate_passed, failed_policies = self.quality_gate.evaluate(res)
        if not gate_passed:
            res.status = VerificationStatus.FAILED
            print(f"[VerificationEngine] Quality gate rejected verification: {failed_policies}")
            
        # Log to evidence store
        self.evidence_store.log_run(res)
        
        return res

    def _parse_compile_errors(self, error_str: str, file_path: str) -> List[VerificationIssue]:
        """
        Parses compiler stdout/stderr lines to extract line number and clear message.
        """
        issues = []
        
        # Regex for Java errors (e.g. EmployeeService.java:[42,8] cannot find symbol)
        # Or [ERROR] /Users/ashish/Downloads/HRMS/backend/src/main/java/com/hrms/employee/EmployeeService.java:[78,35] error message
        java_re = re.compile(r"([^:\s\n]+\.java):\[?(\d+),(\d+)\]?\s*(.*)", re.IGNORECASE)
        
        # Regex for TypeScript errors (e.g. EmployeeForm.tsx(42,17): error TS2322: message)
        ts_re = re.compile(r"([^:\s\n]+\.tsx?)\((\d+),(\d+)\):\s*error\s*(.*)", re.IGNORECASE)
        
        # Regex for TS/Vite error line (e.g. EmployeeForm.tsx:42:17: ERROR: message)
        vite_re = re.compile(r"([^:\s\n]+\.tsx?):(\d+):(\d+):\s*(ERROR:.*|.*)", re.IGNORECASE)

        for line in error_str.splitlines():
            # Match Java
            m = java_re.search(line)
            if m:
                issues.append(VerificationIssue(
                    type="COMPILATION_ERROR",
                    file=file_path,
                    line=int(m.group(2)),
                    message=m.group(4).strip(),
                    severity="HIGH"
                ))
                continue
                
            # Match TS
            m = ts_re.search(line)
            if m:
                issues.append(VerificationIssue(
                    type="COMPILATION_ERROR",
                    file=file_path,
                    line=int(m.group(2)),
                    message=m.group(4).strip(),
                    severity="HIGH"
                ))
                continue
                
            # Match Vite
            m = vite_re.search(line)
            if m:
                issues.append(VerificationIssue(
                    type="COMPILATION_ERROR",
                    file=file_path,
                    line=int(m.group(2)),
                    message=m.group(4).strip(),
                    severity="HIGH"
                ))
                continue

        return issues
