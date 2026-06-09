# verify_verification_and_repair.py
#
# Verification tests for Structured Verification Engine, Classifier, Quality Gates,
# Evidence Store, and Repair Engine orchestrator.

import sys
import os
import tempfile
import json
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from execution.verification_result import (
    VerificationResult, VerificationStatus, VerificationPlan,
    BuildResult, TestResult, LintResult, VerificationIssue, Evidence
)
from execution.failure_classifier import FailureClassifier
from execution.quality_gate import QualityGateEvaluator
from execution.evidence_store import VerificationEvidenceStore
from planning.repair_engine import RepairEngine
from execution.verification_engine import VerificationEngine

class MockFileManager:
    def __init__(self, root):
        self.root = Path(root)
    def resolve_path(self, path):
        return str(self.root / path)

class MockStateManager:
    def __init__(self):
        pass
    def get_state(self):
        return type("State", (), {"failed_steps": []})()

def test_result_compatibility():
    print("[Test] Running VerificationResult and compatibility properties tests...")
    
    build_res = BuildResult(success=False, errors=["Compile error on line 42"])
    test_res = TestResult(success=True)
    lint_res = LintResult(success=True)
    issue = VerificationIssue(
        type="COMPILATION_ERROR",
        file="calc.py",
        line=42,
        message="Compile error on line 42",
        severity="HIGH"
    )
    
    res = VerificationResult(
        status=VerificationStatus.FAILED,
        build_result=build_res,
        lint_result=lint_res,
        test_result=test_res,
        issues=[issue]
    )
    
    assert res.success is False
    assert res.build_passed is False
    assert res.tests_passed is True
    assert res.lint_passed is True
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].line == 42
    assert res.diagnostics[0].message == "Compile error on line 42"
    assert res["success"] is False
    assert res["error"] == "Compile error on line 42"
    
    print("  [OK] VerificationResult compatibility passed.")

def test_failure_classifier():
    print("[Test] Running FailureClassifier tests...")
    classifier = FailureClassifier()
    
    assert classifier.classify("COMPILATION_ERROR", "cannot find symbol class Logger") == "MISSING_IMPORT"
    assert classifier.classify("COMPILATION_ERROR", "cannot find symbol variable x") == "UNDEFINED_SYMBOL"
    assert classifier.classify("SYNTAX_ERROR", "mismatched braces at line 10") == "SYNTAX_ERROR"
    assert classifier.classify("TEST_FAILURE", "AssertionError: expected 5 got 4") == "TEST_REGRESSION"
    assert classifier.classify("COMPILATION_ERROR", "NullPointerException at calc.py") == "NULLABILITY_ERROR"
    assert classifier.classify("LINT_ERROR", "Unused variable") == "LINT_VIOLATION"
    assert classifier.classify("COMPILATION_ERROR", "some other error") == "COMPILATION_FAILURE"
    
    print("  [OK] FailureClassifier passed.")

def test_quality_gate():
    print("[Test] Running QualityGateEvaluator tests...")
    gate = QualityGateEvaluator()
    
    # Perfect run
    res_success = VerificationResult(
        status=VerificationStatus.SUCCESS,
        build_result=BuildResult(success=True),
        lint_result=LintResult(success=True),
        test_result=TestResult(success=True),
        issues=[]
    )
    passed, policies = gate.evaluate(res_success)
    assert passed is True
    assert len(policies) == 0
    
    # Failing build
    res_fail = VerificationResult(
        status=VerificationStatus.FAILED,
        build_result=BuildResult(success=False),
        lint_result=LintResult(success=True),
        test_result=TestResult(success=True),
        issues=[VerificationIssue(type="COMPILATION_ERROR", file="calc.py", line=1, message="fail", severity="HIGH")]
    )
    passed, policies = gate.evaluate(res_fail)
    assert passed is False
    assert "Build / compilation check failed." in policies
    assert "Found 1 critical or high-severity issues." in policies
    
    print("  [OK] QualityGateEvaluator passed.")

def test_evidence_store():
    print("[Test] Running VerificationEvidenceStore tests...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        history_file = os.path.join(tmpdir, "verification_history.json")
        store = VerificationEvidenceStore(history_path=history_file)
        
        # Log a run
        res = VerificationResult(
            status=VerificationStatus.SUCCESS,
            build_result=BuildResult(success=True),
            lint_result=LintResult(success=True),
            test_result=TestResult(success=True)
        )
        store.log_run(res, plan_id="plan_123")
        
        assert os.path.exists(history_file)
        
        history = store.load_history()
        assert len(history) == 1
        assert history[0]["plan_id"] == "plan_123"
        assert history[0]["status"] == "SUCCESS"
        assert history[0]["build_success"] is True
        
    print("  [OK] VerificationEvidenceStore passed.")

def test_repair_engine_and_budget():
    print("[Test] Running RepairEngine and retry budget tests...")
    
    # Mock LLM and state
    class MockLLM:
        def chat(self, messages):
            return json.dumps({
                "repairs": [
                    {
                        "type": "repair_imports",
                        "target": "calc.py",
                        "description": "Fix imports"
                    }
                ]
            })
            
    engine = RepairEngine(llm=MockLLM(), max_attempts=3)
    plan_id = "test_plan_abc"
    
    # Check initial budget
    assert engine.check_budget(plan_id) is True
    
    # Trigger first repair
    res = VerificationResult(
        status=VerificationStatus.FAILED,
        build_result=BuildResult(success=False),
        lint_result=LintResult(success=True),
        test_result=TestResult(success=True),
        issues=[VerificationIssue(type="COMPILATION_ERROR", file="calc.py", line=1, message="cannot find symbol Logger", severity="HIGH")]
    )
    
    tasks = engine.repair(res, "Goal", key=plan_id)
    assert len(tasks) == 1
    assert tasks[0].type.value == "repair_imports"
    assert engine.get_attempts(plan_id) == 1
    assert engine.check_budget(plan_id) is True
    
    # Classify check
    assert res.issues[0].category == "MISSING_IMPORT"
    
    # Reach limits
    engine.increment_attempts(plan_id)
    engine.increment_attempts(plan_id)
    assert engine.check_budget(plan_id) is False
    assert engine.get_attempts(plan_id) == 3
    
    print("  [OK] RepairEngine and retry budget passed.")

def test_verification_engine_flow():
    print("[Test] Running VerificationEngine end-to-end integration tests...")
    
    # Mock resources
    class MockValidator:
        def validate_file_syntax(self, path): pass
    class MockCompileValidator:
        def validate(self, path): pass
    class MockTestRunner:
        def run_backend_tests(self, test_filter=None):
            return {"success": True}
            
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "calc.py")
        Path(file_path).write_text("class Calc: pass", encoding="utf-8")
        
        file_mgr = MockFileManager(tmpdir)
        state_mgr = MockStateManager()
        
        engine = VerificationEngine(
            file_manager=file_mgr,
            state_manager=state_mgr,
            validator=MockValidator(),
            compile_validator=MockCompileValidator(),
            test_runner=MockTestRunner()
        )
        
        # Override history path to temp directory
        engine.evidence_store.history_path = os.path.join(tmpdir, "verification_history.json")
        
        plan = VerificationPlan(stages=["syntax", "build", "tests"], affected_files=["calc.py"])
        res = engine.verify(plan)
        
        assert res.status == VerificationStatus.SUCCESS
        assert res.build_passed is True
        assert res.tests_passed is True
        assert len(res.issues) == 0
        assert len(res.evidence) == 1
        
    print("  [OK] VerificationEngine integration passed.")

def run_all_tests():
    print("\n" + "=" * 60)
    print("  Structured Verification & Auto-Repair Tests")
    print("=" * 60)
    
    try:
        test_result_compatibility()
        test_failure_classifier()
        test_quality_gate()
        test_evidence_store()
        test_repair_engine_and_budget()
        test_verification_engine_flow()
        print("\n" + "=" * 60)
        print("  ALL VERIFICATION & REPAIR TESTS PASSED SUCCESSFULLY! [OK]")
        print("=" * 60 + "\n")
    except AssertionError as ae:
        print(f"\n[FAIL] Assertion Failure: {ae}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
