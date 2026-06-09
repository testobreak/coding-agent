# verify_experience_memory.py
#
# Automated test suite for Phase 11: Execution & Experience Memory Subsystem.

import os
import sys
import json
from pathlib import Path

# Use a local test SQLite database file and set env var
TEST_DB_FILE = "test_experience.db"
os.environ["EXPERIENCE_DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE}"

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from memory.experience_models import create_experience_tables, SessionLocal, ExecutionEpisode, ExecutionEvent
from memory.experience_store import ExecutionMemory
from memory.experience_retriever import ExperienceRetriever
from context.context_builder import ContextBuilder
from context.context_package import ContextPackage
from planning.task_node import TaskNode
from planning.task_types import TaskType
from planning.task_status import TaskStatus
from planning.execution_plan import ExecutionPlan
from runtime.execution_engine import ExecutionEngine

# Mock objects for test isolation
class MockFileManager:
    root = "."
    def resolve_path(self, path):
        return path

class MockStateManager:
    def __init__(self, plan=None):
        self.plan = plan
        self.exec_state = "PLANNING"
        class MockState:
            def __init__(self):
                self.completed_steps = []
                self.failed_steps = []
        self.state = MockState()

    def get_execution_plan(self):
        return self.plan

    def set_execution_plan(self, plan):
        self.plan = plan

    def get_state(self):
        return self.state

    def set_execution_state(self, val):
        self.exec_state = val

    def get_execution_state(self):
        return self.exec_state

    def save_state(self):
        pass

class MockExecutor:
    def __init__(self):
        self.file_manager = MockFileManager()
        
        class MockValidator:
            def validate_file_syntax(self, path):
                pass
        self.validator = MockValidator()
        
        class MockCompileValidator:
            def validate(self, path):
                pass
        self.compile_validator = MockCompileValidator()
        
        class MockTestRunner:
            def run_backend_tests(self, test_filter=None):
                return {"success": True}
        self.tests = MockTestRunner()
        
        self.impact_analyzer = None
        
        class MockModifier:
            llm = None
        self.modifier = MockModifier()
        
        class MockRetrievalPipeline:
            pass
        self.retrieval_pipeline = MockRetrievalPipeline()

    def dispatch(self, tool, args):
        return {"success": True}

def test_database_logging():
    print("[Test] Running database logging tests...")
    memory = ExecutionMemory()
    
    # 1. Start episode
    plan_id = "test_plan_uuid_123"
    memory.start_episode(
        goal="Add logging to EmployeeService",
        plan_id=plan_id,
        repository_id="test_repo"
    )
    
    # Verify episode created
    session = SessionLocal()
    ep = session.query(ExecutionEpisode).filter(ExecutionEpisode.episode_id == plan_id).first()
    assert ep is not None
    assert ep.goal == "Add logging to EmployeeService"
    assert ep.outcome == "PENDING"
    
    # Verify event logged
    evt = session.query(ExecutionEvent).filter(
        ExecutionEvent.episode_id == plan_id, 
        ExecutionEvent.event_type == "PLAN_CREATED"
    ).first()
    assert evt is not None
    
    # 2. Log plan
    memory.log_plan(plan_id, "add_feature", {"objective": "logging"})
    
    # 3. Log event
    memory.log_event(plan_id, "BUILD_STARTED")
    
    # 4. Log failure
    fail_id = memory.log_failure(
        episode_id=plan_id,
        failure_type="MISSING_IMPORT",
        file_path="src/EmployeeService.java",
        line=12,
        symbol="Logger",
        message="Cannot find symbol Logger"
    )
    assert fail_id > 0
    
    # 5. Log repair
    memory.log_repair(
        episode_id=plan_id,
        failure_id=fail_id,
        repair_type="repair_imports",
        target="src/EmployeeService.java",
        patch="import java.util.logging.Logger;",
        description="Add missing logger import",
        success=True
    )
    
    # 6. Complete episode
    memory.complete_episode(plan_id, "SUCCESS")
    
    # Verify outcome updated
    session.expire_all()
    ep = session.query(ExecutionEpisode).filter(ExecutionEpisode.episode_id == plan_id).first()
    assert ep.outcome == "SUCCESS"
    
    session.close()
    print("  [OK] Database logging tests passed.")

def test_experience_retrieval():
    print("[Test] Running experience retrieval tests...")
    retriever = ExperienceRetriever()
    
    # Query similar episodes
    sim = retriever.find_similar_episodes("logging EmployeeService")
    assert len(sim) >= 1
    assert sim[0]["episode_id"] == "test_plan_uuid_123"
    assert "MISSING_IMPORT" in sim[0]["failures_encountered"]
    
    # Query successful plans
    plans = retriever.get_successful_plans("add_feature")
    assert len(plans) >= 1
    assert plans[0]["plan"]["objective"] == "logging"
    
    # Query successful repairs
    repairs = retriever.get_failure_repairs("MISSING_IMPORT")
    assert len(repairs) >= 1
    assert repairs[0]["repair_type"] == "repair_imports"
    assert "Logger" in repairs[0]["patch"]
    
    print("  [OK] Experience retrieval tests passed.")

def test_context_builder_integration():
    print("[Test] Running ContextBuilder integration tests...")
    executor = MockExecutor()
    builder = ContextBuilder(executor.retrieval_pipeline)
    
    # Run build_planning_context
    context = builder.build_planning_context(goal="Add logging to EmployeeService")
    
    # Verify new memory fields populated on ContextPackage
    assert hasattr(context, "past_episodes")
    assert hasattr(context, "past_plans")
    assert hasattr(context, "past_repairs")
    assert len(context.past_episodes) >= 1
    assert context.past_episodes[0]["episode_id"] == "test_plan_uuid_123"
    assert len(context.past_plans) >= 1
    assert len(context.past_repairs) >= 1
    
    # Verify serialization
    data = context.to_dict()
    assert "past_episodes" in data
    assert "past_plans" in data
    assert "past_repairs" in data
    
    deserialized = ContextPackage.from_dict(data)
    assert len(deserialized.past_episodes) >= 1
    assert len(deserialized.past_plans) >= 1
    
    print("  [OK] ContextBuilder integration tests passed.")

def test_execution_engine_integration():
    print("[Test] Running ExecutionEngine integration tests...")
    executor = MockExecutor()
    
    # Build plan
    t_mod = TaskNode(id="T_mod", type=TaskType.MODIFY_SYMBOL, target_symbol="Service.java", status=TaskStatus.COMPLETED)
    t1 = TaskNode(id="T1", type=TaskType.VERIFY_BUILD, target_symbol="Service.java", dependencies=["T_mod"])
    plan = ExecutionPlan(goal="Add logging test", plan_id="engine_test_plan_1", tasks=[t_mod, t1])
    
    state_mgr = MockStateManager(plan)
    engine = ExecutionEngine(executor, state_mgr)
    
    # Execute
    engine.run()
    
    # Verify task status and database logging
    session = SessionLocal()
    ep = session.query(ExecutionEpisode).filter(ExecutionEpisode.episode_id == "engine_test_plan_1").first()
    assert ep is not None
    assert ep.goal == "Add logging test"
    
    # Verify TASK_STARTED event logged for T1
    evt = session.query(ExecutionEvent).filter(
        ExecutionEvent.episode_id == "engine_test_plan_1", 
        ExecutionEvent.event_type == "TASK_STARTED"
    ).first()
    assert evt is not None
    
    session.close()
    print("  [OK] ExecutionEngine integration tests passed.")

def run_all_tests():
    print("\n" + "=" * 60)
    print("  Execution & Experience Memory Subsystem Tests")
    print("=" * 60)
    
    # Ensure fresh start for database
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)
        
    try:
        test_database_logging()
        test_experience_retrieval()
        test_context_builder_integration()
        test_execution_engine_integration()
        print("\n" + "=" * 60)
        print("  ALL EXECUTION MEMORY TESTS PASSED! [OK]")
        print("=" * 60 + "\n")
    except Exception as e:
        print(f"\n[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup test DB
        if os.path.exists(TEST_DB_FILE):
            try:
                os.remove(TEST_DB_FILE)
            except Exception:
                pass

if __name__ == "__main__":
    run_all_tests()
