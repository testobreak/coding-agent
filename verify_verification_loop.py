# verify_verification_loop.py
#
# Automated tests for the Verification Engine, Diagnostics Parsing, Repair Planner, and State Machine.

import sys
import os
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from execution.execution_state import ExecutionState
from execution.verification_result import Diagnostic, VerificationResult, VerificationPlan
from execution.verification_engine import VerificationEngine
from planning.repair_planner import RepairPlanner
from planning.task_node import TaskNode
from planning.task_types import TaskType
from planning.task_status import TaskStatus
from planning.execution_plan import ExecutionPlan
from runtime.execution_engine import ExecutionEngine as RealExecutionEngine

# Mock classes for tests
class MockFileManager:
    def resolve_path(self, path):
        return path

class MockStateManager:
    def __init__(self, plan):
        self.plan = plan
        from memory.task_state import TaskState
        self.state = TaskState(goal=plan.goal)
        self.state.execution_plan = plan.to_dict()
        self.exec_state = "PLANNING"

    def get_execution_plan(self):
        if not self.state.execution_plan:
            return None
        return ExecutionPlan.from_dict(self.state.execution_plan)

    def set_execution_plan(self, plan):
        self.state.execution_plan = plan.to_dict() if plan else None

    def get_state(self):
        return self.state

    def set_execution_state(self, val):
        self.exec_state = val

    def get_execution_state(self):
        return self.exec_state

    def save_state(self):
        pass

class MockValidator:
    def validate_file_syntax(self, path):
        if "syntax_error" in path:
            raise ValueError("Mismatched braces at line 12")

class MockCompileValidator:
    def validate(self, path):
        if "compile_error" in path:
            # Simulate Maven compile error output format
            raise RuntimeError("[ERROR] /src/Service.java:[42,8] cannot find symbol\n  symbol:   class Logger")

class MockTestRunner:
    def run_backend_tests(self, test_filter=None):
        if test_filter == "FailTest":
            return {
                "success": False,
                "failures": [
                    {
                        "test_class": "ServiceTest",
                        "test_method": "testSave",
                        "error_type": "AssertionError",
                        "message": "Expected 200, got 500",
                        "likely_source_files": ["src/Service.java"]
                    }
                ]
            }
        return {"success": True}

class MockExecutor:
    def __init__(self):
        self.file_manager = MockFileManager()
        self.validator = MockValidator()
        self.compile_validator = MockCompileValidator()
        self.tests = MockTestRunner()
        self.impact_analyzer = None
        
        class MockModifier:
            llm = None
        self.modifier = MockModifier()

    def dispatch(self, tool, args):
        return {"success": True, "result": "mock_success"}

def test_diagnostics_parsing():
    print("[Test] Testing compilation error parser...")
    engine = VerificationEngine(None, None, None, None, None, None)
    
    # Simulate TypeScript and Java compile error formats
    java_err = "[ERROR] /src/main/java/com/hrms/EmployeeService.java:[54,12] cannot find symbol\n  symbol:   class Logger"
    ts_err = "src/features/EmployeeForm.tsx(10,5): error TS2322: Type 'string' is not assignable to type 'number'"
    vite_err = "src/features/EmployeeForm.tsx:20:15: ERROR: Transform failed"
    
    java_diags = engine._parse_compile_errors(java_err, "EmployeeService.java")
    assert len(java_diags) == 1
    assert java_diags[0].line == 54
    assert "cannot find symbol" in java_diags[0].message
    
    ts_diags = engine._parse_compile_errors(ts_err, "EmployeeForm.tsx")
    assert len(ts_diags) == 1
    assert ts_diags[0].line == 10
    assert "TS2322" in ts_diags[0].message
    
    vite_diags = engine._parse_compile_errors(vite_err, "EmployeeForm.tsx")
    assert len(vite_diags) == 1
    assert vite_diags[0].line == 20
    assert "Transform failed" in vite_diags[0].message
    
    print("  [OK] Diagnostics error parsing passed.")

def test_progressive_verification():
    print("[Test] Testing progressive verification engine...")
    executor = MockExecutor()
    engine = VerificationEngine(
        file_manager=executor.file_manager,
        state_manager=None,
        validator=executor.validator,
        compile_validator=executor.compile_validator,
        test_runner=executor.tests
    )
    
    # 1. Syntax Failure
    plan_syntax = VerificationPlan(stages=["syntax"], affected_files=["syntax_error.java"])
    res = engine.verify(plan_syntax)
    assert not res.success
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].type == "syntax_error"
    
    # 2. Compile Failure
    plan_compile = VerificationPlan(stages=["syntax", "build"], affected_files=["compile_error.java"])
    res = engine.verify(plan_compile)
    assert not res.success
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].type == "compile_error"
    assert res.diagnostics[0].line == 42
    
    # 3. Test Failure
    plan_test = VerificationPlan(stages=["tests"], test_filter="FailTest", affected_files=["src/Service.java"])
    res = engine.verify(plan_test)
    assert not res.success
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].type == "test_failure"
    assert "ServiceTest.testSave" in res.diagnostics[0].symbol
    
    print("  [OK] Progressive verification engine passed.")

def test_repair_planner_and_retry_budget():
    print("[Test] Testing RepairPlanner and repair budget enforcement...")
    
    # Construct a plan
    t_mod = TaskNode(id="T_mod", type=TaskType.MODIFY_SYMBOL, target_symbol="compile_error.java", status=TaskStatus.COMPLETED)
    t1 = TaskNode(id="T1", type=TaskType.VERIFY_BUILD, target_symbol="MyClass", dependencies=["T_mod"])
    plan = ExecutionPlan(goal="Fix error", tasks=[t_mod, t1])
    
    state_mgr = MockStateManager(plan)
    executor = MockExecutor()
    engine = RealExecutionEngine(executor, state_mgr)
    
    # Mock compile failure file in state to trigger build validation failure
    t1.payload["file_path"] = "compile_error.java"
    state_mgr.set_execution_plan(plan)
    
    # Execute t1 (which will fail compile validation, invoke RepairPlanner and inject a repair task)
    res = engine.run()
    
    # Assert state transitions to REPAIRING
    assert state_mgr.get_execution_state() == ExecutionState.REPAIRING.value
    
    # Assert a repair task was injected
    updated_plan = state_mgr.get_execution_plan()
    repair_tasks = [t for t in updated_plan.tasks if t.type in (TaskType.REPAIR_COMPILATION, TaskType.REPAIR_SYMBOL, TaskType.REPAIR_IMPORTS)]
    assert len(repair_tasks) == 1, f"Expected 1 repair task to be injected, got: {len(repair_tasks)}"
    t1_updated = updated_plan.find_task("T1")
    print(f"DEBUG: t1_updated.dependencies={t1_updated.dependencies}")
    print(f"DEBUG: t1_updated.status={t1_updated.status}")
    print(f"DEBUG: repair_tasks[0].id={repair_tasks[0].id}")
    assert repair_tasks[0].id in t1_updated.dependencies
    assert t1_updated.status == TaskStatus.PENDING, "Failed verification task should be reset to PENDING"
    
    # Simulate running again to trigger repair task budget count (inserting up to 3 repair tasks)
    # We simulate 3 repair tasks in plan that are already completed
    updated_plan.tasks = [
        t_mod,
        TaskNode(id="rep1", type=TaskType.REPAIR_COMPILATION, status=TaskStatus.COMPLETED),
        TaskNode(id="rep2", type=TaskType.REPAIR_COMPILATION, status=TaskStatus.COMPLETED),
        TaskNode(id="rep3", type=TaskType.REPAIR_COMPILATION, status=TaskStatus.COMPLETED),
        t1_updated
    ]
    t1_updated.status = TaskStatus.PENDING
    t1_updated.dependencies = ["T_mod", "rep1", "rep2", "rep3"]
    state_mgr.set_execution_plan(updated_plan)
    
    # Run again - should hit repair budget and fail
    engine.run()
    final_plan = state_mgr.get_execution_plan()
    assert final_plan.find_task("T1").status == TaskStatus.FAILED, "Expected task to fail after repair budget exhausted"
    
    print("  [OK] RepairPlanner and retry budget test passed.")

def run_all_tests():
    print("\n" + "=" * 60)
    print("  Verification Loop & Repair Planner Tests")
    print("=" * 60)
    
    # Create temp files
    os.makedirs("src", exist_ok=True)
    for p in ["syntax_error.java", "compile_error.java", "src/Service.java"]:
        with open(p, "w") as f:
            f.write("// dummy code")

    try:
        test_diagnostics_parsing()
        test_progressive_verification()
        test_repair_planner_and_retry_budget()
        print("\n" + "=" * 60)
        print("  ALL VERIFICATION LOOP TESTS PASSED! [OK]")
        print("=" * 60 + "\n")
    except Exception as e:
        print(f"\n[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        for p in ["syntax_error.java", "compile_error.java", "src/Service.java"]:
            if os.path.exists(p):
                os.remove(p)
        try:
            os.rmdir("src")
        except Exception:
            pass

if __name__ == "__main__":
    run_all_tests()
