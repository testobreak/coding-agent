# verify_plan_dag.py
#
# Integration and unit tests for the Task DAG Planning, Validation, and Execution subsystem.

import sys
import os
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from planning.task_types import TaskType
from planning.task_status import TaskStatus
from planning.task_node import TaskNode
from planning.execution_plan import ExecutionPlan
from planning.plan_validator import PlanValidator
from runtime.execution_engine import ExecutionEngine
from memory.state_manager import StateManager
from memory.task_state import TaskState

class MockFileManager:
    def resolve_path(self, path):
        return path

class MockValidator:
    def validate_file_syntax(self, path):
        pass

class MockCompileValidator:
    def validate(self, path):
        pass

class MockTestRunner:
    def run_backend_tests(self, test_filter=None):
        return {"success": True}

class MockExecutor:
    def __init__(self):
        self.dispatched = []
        self.file_manager = MockFileManager()
        self.validator = MockValidator()
        self.compile_validator = MockCompileValidator()
        self.tests = MockTestRunner()
        self.impact_analyzer = None
        class MockModifier:
            llm = None
        self.modifier = MockModifier()

    def dispatch(self, tool, args):
        self.dispatched.append((tool, args))
        # Return success for mock runs
        return {"success": True, "tool": tool, "result": "mock_success"}

class MockStateManager:
    def __init__(self, plan: ExecutionPlan):
        self.plan = plan
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

def test_dag_operations():
    print("[Test] Running DAG operations and cycle detection tests...")
    
    # 1. Valid linear DAG: T1 -> T2 -> T3
    t1 = TaskNode(id="T1", type=TaskType.MODIFY_SYMBOL, target_symbol="MyClass", dependencies=[])
    t2 = TaskNode(id="T2", type=TaskType.VERIFY_BUILD, dependencies=["T1"])
    t3 = TaskNode(id="T3", type=TaskType.RUN_TEST, dependencies=["T2"])
    
    plan = ExecutionPlan(goal="Test goal", tasks=[t1, t2, t3])
    
    assert not plan.has_cycles(), "Valid plan identified as cyclic!"
    assert plan.get_runnable_tasks() == [t1], f"Expected runnable task: T1, got: {[t.id for t in plan.get_runnable_tasks()]}"
    
    # Simulate execution of T1
    plan.mark_completed("T1")
    assert plan.get_runnable_tasks() == [t2], f"Expected runnable task: T2, got: {[t.id for t in plan.get_runnable_tasks()]}"
    
    # Simulate execution of T2
    plan.mark_completed("T2")
    assert plan.get_runnable_tasks() == [t3], f"Expected runnable task: T3, got: {[t.id for t in plan.get_runnable_tasks()]}"
    
    # Simulate execution of T3
    plan.mark_completed("T3")
    assert plan.is_finished(), "Plan should be finished"
    assert plan.is_successful(), "Plan should be successful"
    
    # 2. Cyclic DAG: T1 -> T2 -> T3 -> T1
    t1.dependencies = ["T3"]
    plan_cyclic = ExecutionPlan(goal="Cyclic goal", tasks=[t1, t2, t3])
    assert plan_cyclic.has_cycles(), "Cyclic plan not identified as cyclic!"
    
    print("  [OK] DAG operations and cycle detection passed.")

def test_failure_propagation():
    print("[Test] Running failure propagation tests...")
    
    # T1 -> T2 -> T3
    # T4 (independent)
    t1 = TaskNode(id="T1", type=TaskType.MODIFY_SYMBOL, target_symbol="MyClass", dependencies=[])
    t2 = TaskNode(id="T2", type=TaskType.VERIFY_BUILD, dependencies=["T1"])
    t3 = TaskNode(id="T3", type=TaskType.RUN_TEST, dependencies=["T2"])
    t4 = TaskNode(id="T4", type=TaskType.MODIFY_SYMBOL, target_symbol="AnotherClass", dependencies=[])
    
    plan = ExecutionPlan(goal="Failure test", tasks=[t1, t2, t3, t4])
    
    # Fail T1
    plan.mark_failed("T1")
    
    # T2 and T3 should be skipped
    assert plan.find_task("T1").status == TaskStatus.FAILED
    assert plan.find_task("T2").status == TaskStatus.SKIPPED
    assert plan.find_task("T3").status == TaskStatus.SKIPPED
    
    # T4 should remain PENDING
    assert plan.find_task("T4").status == TaskStatus.PENDING
    assert plan.get_runnable_tasks() == [t4], "T4 should be the only runnable task now"
    
    print("  [OK] Failure propagation passed.")

def test_validator():
    print("[Test] Running PlanValidator tests...")
    
    # Create mock database mapping where "EmployeeService" exists but "FakeService" doesn't
    # In verify_context_builder.py, we created DB schema but here we can just test with paths
    validator = PlanValidator(repo_root=os.path.abspath(os.path.dirname(__file__)))
    
    # Test valid task with existing file (verify_plan_dag.py exists in repo_root)
    t_valid = TaskNode(id="T1", type=TaskType.MODIFY_SYMBOL, target_symbol="verify_plan_dag.py")
    plan_valid = ExecutionPlan(goal="Validate", tasks=[t_valid])
    errors = validator.validate(plan_valid)
    assert not errors, f"Expected no validation errors, got: {errors}"
    
    # Test invalid target symbol
    t_invalid = TaskNode(id="T2", type=TaskType.MODIFY_SYMBOL, target_symbol="FakeNonExistentSymbol")
    plan_invalid = ExecutionPlan(goal="Validate", tasks=[t_invalid])
    errors = validator.validate(plan_invalid)
    assert any("could not be resolved" in err for err in errors), f"Expected resolution error, got: {errors}"
    
    # Test missing dependency
    t_missing_dep = TaskNode(id="T3", type=TaskType.VERIFY_BUILD, dependencies=["T_NON_EXISTENT"])
    plan_missing = ExecutionPlan(goal="Validate", tasks=[t_missing_dep])
    errors = validator.validate(plan_missing)
    assert any("depends on non-existent task" in err for err in errors), f"Expected missing dependency error, got: {errors}"
    
    print("  [OK] PlanValidator passed.")

def test_execution_engine():
    print("[Test] Running ExecutionEngine DAG run tests...")
    
    t1 = TaskNode(id="T1", type=TaskType.MODIFY_SYMBOL, target_symbol="verify_plan_dag.py", description="Modify main class")
    t2 = TaskNode(id="T2", type=TaskType.RUN_TEST, dependencies=["T1"], description="Run unit tests")
    
    plan = ExecutionPlan(goal="Execute", tasks=[t1, t2])
    
    executor = MockExecutor()
    state_mgr = MockStateManager(plan)
    engine = ExecutionEngine(executor, state_mgr)
    
    # Run T1
    res1 = engine.run()
    assert res1["success"], "T1 execution should succeed"
    assert executor.dispatched[-1][0] == "modify_symbol", f"Expected modify_symbol dispatch, got: {executor.dispatched[-1]}"
    
    # Retrieve updated plan
    updated_plan = state_mgr.get_execution_plan()
    assert updated_plan.find_task("T1").status == TaskStatus.COMPLETED
    assert updated_plan.find_task("T2").status == TaskStatus.PENDING
    
    # Run T2
    res2 = engine.run()
    assert res2["success"], "T2 execution should succeed"
    
    # Retrieve updated plan
    updated_plan2 = state_mgr.get_execution_plan()
    assert updated_plan2.find_task("T2").status == TaskStatus.COMPLETED
    assert updated_plan2.is_finished()
    
    print("  [OK] ExecutionEngine DAG run passed.")

def test_planning_strategy():
    print("[Test] Running PlanningStrategy selection tests...")
    from planning.planning_strategy import PlanningStrategy
    from context.context_package import ContextPackage, GoalIntent

    # 1. Test REPAIR strategy selection
    ctx = ContextPackage(
        goal="Fix issue",
        primary_symbol=None,
        previous_attempts=["Failed compile"]
    )
    assert PlanningStrategy.from_context(ctx) == PlanningStrategy.REPAIR

    # 2. Test BUGFIX action mappings
    for action in ["modify", "fix", "bug", "debug"]:
        ctx = ContextPackage(
            goal="Fix bug",
            primary_symbol=None,
            intent=GoalIntent(action=action, target="MyClass", domain="service", confidence=1.0)
        )
        assert PlanningStrategy.from_context(ctx) == PlanningStrategy.BUGFIX

    # 3. Test FEATURE action mappings
    for action in ["add_feature", "create", "implement", "add"]:
        ctx = ContextPackage(
            goal="Add feature",
            primary_symbol=None,
            intent=GoalIntent(action=action, target="MyClass", domain="service", confidence=1.0)
        )
        assert PlanningStrategy.from_context(ctx) == PlanningStrategy.FEATURE

    # 4. Test REFACTOR action mappings
    for action in ["refactor", "cleanup", "optimize"]:
        ctx = ContextPackage(
            goal="Refactor class",
            primary_symbol=None,
            intent=GoalIntent(action=action, target="MyClass", domain="service", confidence=1.0)
        )
        assert PlanningStrategy.from_context(ctx) == PlanningStrategy.REFACTOR

    # 5. Test ANALYSIS action mappings
    for action in ["analyze", "explain", "review", "summary"]:
        ctx = ContextPackage(
            goal="Analyze codebase",
            primary_symbol=None,
            intent=GoalIntent(action=action, target="MyClass", domain="service", confidence=1.0)
        )
        assert PlanningStrategy.from_context(ctx) == PlanningStrategy.ANALYSIS

    # 6. Test TEST_ONLY action mappings
    for action in ["test", "test_only"]:
        ctx = ContextPackage(
            goal="Run tests",
            primary_symbol=None,
            intent=GoalIntent(action=action, target="MyClass", domain="service", confidence=1.0)
        )
        assert PlanningStrategy.from_context(ctx) == PlanningStrategy.TEST_ONLY

    # 7. Test fallback to FEATURE
    ctx = ContextPackage(
        goal="Unknown goal",
        primary_symbol=None,
        intent=GoalIntent(action="unknown", target="MyClass", domain="service", confidence=1.0)
    )
    assert PlanningStrategy.from_context(ctx) == PlanningStrategy.FEATURE

    print("  [OK] PlanningStrategy selection passed.")

def test_plan_compiler_strategies():
    print("[Test] Running PlanCompiler strategy-driven compilation tests...")
    from planning.plan_compiler import PlanCompiler
    from planning.planning_strategy import PlanningStrategy
    from context.context_package import ContextPackage, GoalIntent
    from editing.symbol_handle import SymbolHandle

    compiler = PlanCompiler()

    # Create dummy handles
    primary_sh = SymbolHandle("sym_1", "EmployeeService.saveEmployee", "method", "EmployeeService.py", 10, 20)
    caller_sh = SymbolHandle("sym_2", "EmployeeController.create", "method", "EmployeeController.py", 5, 15)
    test_sh = SymbolHandle("sym_3", "EmployeeServiceTest.testSave", "method", "EmployeeServiceTest.py", 1, 100)

    # 1. FEATURE compile check
    ctx_feature = ContextPackage(
        goal="Implement saving",
        primary_symbol=primary_sh,
        related_tests=[test_sh],
        intent=GoalIntent(action="create", target="EmployeeService.saveEmployee", domain="service", confidence=1.0)
    )
    plan_feature = compiler.compile(ctx_feature)
    assert plan_feature.strategy == PlanningStrategy.FEATURE
    task_ids = [t.id for t in plan_feature.tasks]
    assert "modify_0" in task_ids
    assert "update_test_0" in task_ids
    assert "build" in task_ids
    assert "test" in task_ids
    assert "commit" in task_ids

    modify_node = plan_feature.find_task("modify_0")
    update_test_node = plan_feature.find_task("update_test_0")
    build_node = plan_feature.find_task("build")
    test_node = plan_feature.find_task("test")
    commit_node = plan_feature.find_task("commit")

    assert modify_node.target_symbol == "EmployeeService.saveEmployee"
    assert modify_node.payload.get("file_path") == "EmployeeService.py"
    assert update_test_node.target_symbol == "EmployeeServiceTest.testSave"
    assert "modify_0" in update_test_node.dependencies
    assert "modify_0" in build_node.dependencies
    assert "update_test_0" in build_node.dependencies
    assert "build" in test_node.dependencies
    assert "test" in commit_node.dependencies

    # 2. BUGFIX compile check
    ctx_bugfix = ContextPackage(
        goal="Fix issue",
        primary_symbol=primary_sh,
        intent=GoalIntent(action="fix", target="EmployeeService.saveEmployee", domain="service", confidence=1.0)
    )
    plan_bugfix = compiler.compile(ctx_bugfix)
    assert plan_bugfix.strategy == PlanningStrategy.BUGFIX
    task_ids_bf = [t.id for t in plan_bugfix.tasks]
    assert task_ids_bf == ["analyze", "fix_0", "build", "test", "commit"]
    assert plan_bugfix.find_task("fix_0").target_symbol == "EmployeeService.saveEmployee"
    assert plan_bugfix.find_task("fix_0").payload.get("file_path") == "EmployeeService.py"

    # 3. REFACTOR compile check
    ctx_refactor = ContextPackage(
        goal="Clean up",
        primary_symbol=primary_sh,
        callers=[caller_sh],
        intent=GoalIntent(action="refactor", target="EmployeeService.saveEmployee", domain="service", confidence=1.0)
    )
    plan_refactor = compiler.compile(ctx_refactor)
    assert plan_refactor.strategy == PlanningStrategy.REFACTOR
    task_ids_rf = [t.id for t in plan_refactor.tasks]
    assert "modify_0" in task_ids_rf
    assert "modify_caller_0" in task_ids_rf
    assert "build" in task_ids_rf
    assert "test" in task_ids_rf
    assert "commit" in task_ids_rf
    assert plan_refactor.find_task("modify_caller_0").target_symbol == "EmployeeController.create"

    # 4. TEST_ONLY compile check
    ctx_test = ContextPackage(
        goal="Add tests",
        primary_symbol=primary_sh,
        related_tests=[test_sh],
        intent=GoalIntent(action="test", target="EmployeeService.saveEmployee", domain="service", confidence=1.0)
    )
    plan_test = compiler.compile(ctx_test)
    assert plan_test.strategy == PlanningStrategy.TEST_ONLY
    task_ids_to = [t.id for t in plan_test.tasks]
    assert "update_test_0" in task_ids_to
    assert "test" in task_ids_to

    # 5. ANALYSIS compile check
    ctx_analysis = ContextPackage(
        goal="Explain this",
        primary_symbol=primary_sh,
        intent=GoalIntent(action="analyze", target="EmployeeService.saveEmployee", domain="service", confidence=1.0)
    )
    plan_analysis = compiler.compile(ctx_analysis)
    assert plan_analysis.strategy == PlanningStrategy.ANALYSIS
    assert [t.id for t in plan_analysis.tasks] == ["analyze"]

    # 6. REPAIR compile check
    ctx_repair = ContextPackage(
        goal="Retry fix",
        primary_symbol=primary_sh,
        previous_attempts=["Attempt 1 failed with compiler error"]
    )
    plan_repair = compiler.compile(ctx_repair)
    assert plan_repair.strategy == PlanningStrategy.REPAIR
    task_ids_rp = [t.id for t in plan_repair.tasks]
    assert task_ids_rp == ["analyze", "repair_0", "build", "test", "commit"]
    assert plan_repair.find_task("repair_0").target_symbol == "EmployeeService.saveEmployee"
    assert plan_repair.find_task("analyze").payload.get("previous_attempts") == ["Attempt 1 failed with compiler error"]

    print("  [OK] PlanCompiler strategies passed.")

def test_risk_aware_lint_injection():
    print("[Test] Running risk-aware lint injection tests...")
    from planning.plan_compiler import PlanCompiler
    from planning.task_types import TaskType
    from context.context_package import ContextPackage, GoalIntent
    from editing.symbol_handle import SymbolHandle

    compiler = PlanCompiler()
    primary_sh = SymbolHandle("sym_1", "EmployeeService.saveEmployee", "method", "EmployeeService.py", 10, 20)

    # 1. Feature with low risk
    ctx_low = ContextPackage(
        goal="Implement feature",
        primary_symbol=primary_sh,
        risk_score=0.1,
        intent=GoalIntent(action="create", target="EmployeeService", domain="service", confidence=1.0)
    )
    plan_low = compiler.compile(ctx_low)
    assert "lint" not in [t.id for t in plan_low.tasks]
    assert "build" in plan_low.find_task("test").dependencies

    # 2. Feature with high risk
    ctx_high = ContextPackage(
        goal="Implement feature",
        primary_symbol=primary_sh,
        risk_score=0.8,
        intent=GoalIntent(action="create", target="EmployeeService", domain="service", confidence=1.0)
    )
    plan_high = compiler.compile(ctx_high)
    task_ids = [t.id for t in plan_high.tasks]
    assert "lint" in task_ids
    assert plan_high.find_task("lint").type == TaskType.VERIFY_LINT
    assert "build" in plan_high.find_task("test").dependencies
    assert "lint" in plan_high.find_task("test").dependencies

    # 3. Bugfix with low risk
    ctx_bug_low = ContextPackage(
        goal="Fix bug",
        primary_symbol=primary_sh,
        risk_score=0.2,
        intent=GoalIntent(action="fix", target="EmployeeService", domain="service", confidence=1.0)
    )
    plan_bug_low = compiler.compile(ctx_bug_low)
    assert "lint" not in [t.id for t in plan_bug_low.tasks]
    assert "build" in plan_bug_low.find_task("test").dependencies

    # 4. Bugfix with high risk
    ctx_bug_high = ContextPackage(
        goal="Fix bug",
        primary_symbol=primary_sh,
        risk_score=0.9,
        intent=GoalIntent(action="fix", target="EmployeeService", domain="service", confidence=1.0)
    )
    plan_bug_high = compiler.compile(ctx_bug_high)
    task_ids_bh = [t.id for t in plan_bug_high.tasks]
    assert "lint" in task_ids_bh
    assert plan_bug_high.find_task("lint").type == TaskType.VERIFY_LINT
    assert "build" in plan_bug_high.find_task("test").dependencies
    assert "lint" in plan_bug_high.find_task("test").dependencies

    print("  [OK] Risk-aware lint injection passed.")

def test_plan_persistence():
    print("[Test] Running ExecutionPlan persistence tests...")
    import tempfile
    from planning.planning_strategy import PlanningStrategy
    from planning.task_node import TaskNode
    from planning.task_types import TaskType
    from planning.execution_plan import ExecutionPlan

    t1 = TaskNode(id="T1", type=TaskType.MODIFY_SYMBOL, target_symbol="ClassA", payload={"file_path": "ClassA.py"})
    t2 = TaskNode(id="T2", type=TaskType.VERIFY_BUILD, dependencies=["T1"])
    plan = ExecutionPlan(
        goal="Persist me",
        strategy=PlanningStrategy.REFACTOR,
        tasks=[t1, t2]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "plan.json")
        plan.save(file_path)
        assert os.path.exists(file_path)

        loaded_plan = ExecutionPlan.load(file_path)
        assert loaded_plan.plan_id == plan.plan_id
        assert loaded_plan.goal == plan.goal
        assert loaded_plan.strategy == plan.strategy
        assert len(loaded_plan.tasks) == len(plan.tasks)

        t1_loaded = loaded_plan.find_task("T1")
        assert t1_loaded is not None
        assert t1_loaded.type == TaskType.MODIFY_SYMBOL
        assert t1_loaded.target_symbol == "ClassA"
        assert t1_loaded.payload.get("file_path") == "ClassA.py"

        t2_loaded = loaded_plan.find_task("T2")
        assert t2_loaded is not None
        assert t2_loaded.dependencies == ["T1"]

    print("  [OK] ExecutionPlan persistence passed.")

def run_all_tests():
    print("\n" + "=" * 60)
    print("  Task DAG Planning & Execution Subsystem Tests")
    print("=" * 60)
    
    try:
        test_dag_operations()
        test_failure_propagation()
        test_validator()
        test_execution_engine()
        test_planning_strategy()
        test_plan_compiler_strategies()
        test_risk_aware_lint_injection()
        test_plan_persistence()
        print("\n" + "=" * 60)
        print("  ALL TASK DAG TESTS PASSED SUCCESSFULLY! [OK]")
        print("=" * 60 + "\n")
    except AssertionError as ae:
        print(f"\n[FAIL] Assertion Failure: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
