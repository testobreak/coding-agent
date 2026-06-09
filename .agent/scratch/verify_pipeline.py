# scratch/verify_pipeline.py
import sys
import os

# Ensure .agent is on path
agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

print(f"agent_dir: {agent_dir}")
print(f"sys.path: {sys.path}")

print("Checking imports...")
try:
    from runtime.runtime import Runtime
    from llm.llm_planner import LLMPlanner
    from planning.planner import Planner
    print("[OK] All imports succeeded.")
except Exception as e:
    print(f"[FAIL] Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Initializing Runtime...")
try:
    rt = Runtime()
    print("[OK] Runtime initialized successfully.")
    
    # Check that retrieval_pipeline is successfully exposed
    assert rt.retrieval_pipeline is not None, "retrieval_pipeline was not exposed on Runtime"
    print("[OK] retrieval_pipeline exposed on Runtime successfully.")
    
    # Check queries extraction
    queries = rt._extract_search_queries("Add logging to EmployeeService")
    print(f"[OK] Queries extracted successfully: {queries}")
    assert len(queries) > 0, "No queries extracted"
    
    # Check context package building
    dummy_chunk = {
        "file": "src/main/java/com/hrms/service/EmployeeService.java",
        "name": "calculateSalary",
        "type": "MethodDef",
        "code": "public void calculateSalary() {}"
    }
    context = rt._build_context_package([dummy_chunk])
    print(f"[OK] Context package built successfully: {context.keys()}")
    assert len(context["unique_files"]) == 1
    assert len(context["symbols"]) == 1
    
    # Verify planner doesn't fail to create a plan
    from memory.task_state import TaskState
    state = TaskState(goal="Add logging to EmployeeService", task_id="test_task_id")
    state.retrieved_chunks = [dummy_chunk]
    plan = rt.planner.create_plan(state)
    print(f"[OK] Planner created plan successfully (length {len(plan)}).")
    # Verify RETRIEVE actions are skipped when retrieved_chunks is set
    has_retrieve = any(action.action_type == "retrieve" for action in plan)
    print(f"   Skip retrieve check: has_retrieve = {has_retrieve}")
    assert not has_retrieve, "Planner failed to skip retrieve action when chunks already exist"
    print("[OK] Planner successfully skipped RETRIEVE actions because chunks were present.")
    
    print("\nALL PIPELINE VERIFICATIONS PASSED SUCCESSFULLY!")
except Exception as e:
    print(f"[FAIL] Verification failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
