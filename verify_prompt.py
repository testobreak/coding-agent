import sys
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from context.prompt_context import PromptContext
from context.prompt_builder import PromptBuilder


def run_tests():
    print("\n" + "=" * 60)
    print("  PromptBuilder Integration Tests")
    print("=" * 60)

    builder = PromptBuilder()

    # 1. Construct a mock dictionary representing the ContextAssembler's payload
    mock_data = {
        "goal": "Add leaves limit validation to EmployeeService",
        "status": "in_progress",
        "current_step": "modify_file",
        "retrieved_chunks": [
            {
                "file": "backend/src/main/java/com/hrms/employee/EmployeeService.java",
                "symbol": "com.hrms.employee.EmployeeService",
                "code": "public class EmployeeService { ... }",
                "content": "public class EmployeeService { ... }"
            },
            {
                "file": "backend/src/main/java/com/hrms/employee/EmployeeService.java",
                "symbol": "com.hrms.employee.EmployeeService.addLeaves",
                "code": "public void addLeaves(int amount) { /* code body */ }",
                "content": "public void addLeaves(int amount) { /* code body */ }"
            },
            {
                "file": "backend/src/main/java/com/hrms/employee/EmployeeController.java",
                "symbol": "com.hrms.employee.EmployeeController",
                "code": "public class EmployeeController { ... }",
                "content": "public class EmployeeController { ... }"
            },
            # A extremely long chunk content to test the 1500 char truncation rule
            {
                "file": "backend/src/main/java/com/hrms/employee/StaleDao.java",
                "symbol": "com.hrms.employee.StaleDao",
                "code": "public class StaleDao {\n" + ("// " + "A" * 100 + "\n") * 25 + "}",
                "content": "public class StaleDao {\n" + ("// " + "A" * 100 + "\n") * 25 + "}"
            }
        ]
    }

    try:
        # -------------------------------------------------------------
        # Test 1: Dictionary Parsing to PromptContext
        # -------------------------------------------------------------
        print("\n[Test 1] Testing PromptContext.from_dict() parsing...")
        ctx = PromptContext.from_dict(mock_data)
        assert isinstance(ctx, PromptContext), "Expected PromptContext instance"
        assert ctx.goal == mock_data["goal"], "Failed to map core properties"
        assert len(ctx.retrieved_chunks) == len(mock_data["retrieved_chunks"]), "Failed to map list elements"
        print("  [OK] Success: Dictionary successfully parsed to PromptContext dataclass.")

        # -------------------------------------------------------------
        # Test 2: Build Execution Prompt Structure
        # -------------------------------------------------------------
        print("\n[Test 2] Testing build_execution_prompt() layout headers...")
        prompt = builder.build_execution_prompt(mock_data)
        
        # Verify all sections are present
        assert "TASK" in prompt, "Missing TASK section header"
        assert "FILE" in prompt, "Missing FILE section header"
        assert "EXECUTION CONTEXT" in prompt, "Missing EXECUTION CONTEXT section header"
        assert "ARCHITECTURE NOTES" in prompt, "Missing ARCHITECTURE NOTES section header"
        
        print("  [OK] Success: Optimized execution prompt contains all target layout sections.")

        # -------------------------------------------------------------
        # Test 3: Limits & Truncation Rules
        # -------------------------------------------------------------
        print("\n[Test 3] Testing truncation and list limits...")
        
        # Enforce unique paths deduplication (only 3 unique files in our mock)
        assert "- backend/src/main/java/com/hrms/employee/EmployeeService.java" in prompt
        assert "- backend/src/main/java/com/hrms/employee/EmployeeController.java" in prompt
        assert "- backend/src/main/java/com/hrms/employee/StaleDao.java" in prompt
        
        # The extremely long snippet of StaleDao must be truncated to <= 1500 chars
        long_chunk_content = mock_data["retrieved_chunks"][-1]["content"]
        assert len(long_chunk_content) > 2500, "Mock long chunk is not long enough to test truncation"
        
        # Check that the raw 2500+ character body is NOT fully dumped into the prompt,
        # but is capped.
        assert long_chunk_content not in prompt, "Encountered raw chunk exceeding truncation limit"
        assert long_chunk_content[:1500] in prompt, "Enforced truncated chunk was not successfully embedded"
        
        print("  [OK] Success: Token Capping rules (1500 character snippet limit) correctly enforced.")

        print("\n" + "=" * 60)
        print("  ALL PROMPT OPTIMIZATION TESTS PASSED! [OK]")
        print("=" * 60 + "\n")

    except AssertionError as ae:
        print(f"\n[FAIL] ASSERTION ERROR: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
