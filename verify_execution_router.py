# verify_execution_router.py
import sys
import os

# Setup sys path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".agent")))

from core.execution_mode import TaskIntentMode as ExecutionMode
from core.validation_escalator import ValidationEscalator
from core.validation_mode import ValidationMode
from routing.intent_router import IntentRouter

def test_execution_mode_values():
    print("[Test] Verifying Core ExecutionMode values & compatibility...")
    assert ExecutionMode.INLINE.value == 0
    assert ExecutionMode.PATCH.value == 1
    assert ExecutionMode.ASSIST.value == 2
    assert ExecutionMode.AGENT.value == 3

    # Test backward compatibility string / enum equality overrides
    assert ExecutionMode.INLINE == "inline"
    assert ExecutionMode.INLINE == "inline_edit"
    assert ExecutionMode.INLINE == "fast_completion"
    assert ExecutionMode.PATCH == "patch"
    assert ExecutionMode.PATCH == "patch_edit"
    assert ExecutionMode.PATCH == "fast_edit"
    assert ExecutionMode.PATCH == "smart_edit"
    assert ExecutionMode.ASSIST == "assist"
    assert ExecutionMode.ASSIST == "code_assist"
    assert ExecutionMode.AGENT == "agent"
    assert ExecutionMode.AGENT == "multi_file_patch"
    assert ExecutionMode.AGENT == "autonomous_agent"

    # Test integer matching
    assert ExecutionMode.INLINE == 0
    assert ExecutionMode.PATCH == 1
    print("  [OK] ExecutionMode values and comparisons verified.")



def test_validation_escalator():
    print("[Test] Verifying Staged Validation Escalator...")
    # Mode 1: Log only edit -> ValidationMode.NONE
    log_patch = "logger.info('Resetting value');"
    val1 = ValidationEscalator.choose_validation(log_patch, "add logging", ExecutionMode.PATCH)
    assert val1 == ValidationMode.NONE

    # Mode 2: Normal method edit -> ValidationMode.FAST
    method_patch = "x = x + 1"
    val2 = ValidationEscalator.choose_validation(method_patch, "increment x", ExecutionMode.PATCH)
    assert val2 == ValidationMode.FAST

    # Mode 3: Signature modification -> ValidationMode.SEMANTIC
    sig_patch = "public void reset() {\n    x = 0;\n}"
    val3 = ValidationEscalator.choose_validation(sig_patch, "make reset public", ExecutionMode.PATCH)
    assert val3 == ValidationMode.SEMANTIC

    # Mode 4: AGENT execution mode -> ValidationMode.FULL
    val4 = ValidationEscalator.choose_validation("x = x + 1", "increment x", ExecutionMode.AGENT)
    assert val4 == ValidationMode.FULL
    print("  [OK] Staged ValidationEscalator verified.")

def test_symbol_locator():
    print("[Test] Verifying SymbolLocator exact and fallback lookup...")
    import os
    from repository_intelligence.symbol_locator import SymbolLocator
    
    locator = SymbolLocator()
    mock_index = {
        "com.example.UserService.updateUser": {
            "file_path": "backend/src/main/java/com/example/UserService.java",
            "start_line": 120,
            "end_line": 165,
            "type": "method",
            "parent": "UserService"
        }
    }
    original_cache = locator.symbols_cache
    locator.symbols_cache = mock_index
    
    # 1. Exact match
    span1 = locator.locate("com.example.UserService.updateUser")
    assert span1 is not None
    assert span1.start_line == 120
    assert span1.symbol_type == "method"
    
    # 2. Suffix match
    span2 = locator.locate("updateSalary")
    assert span2 is not None
    assert span2.start_line == 120
    
    locator.symbols_cache = original_cache
    print("  [OK] SymbolLocator verification passed.")



def main():
    print("============================================================")
    print("  Execution Router & Validation Escalator Verification Suite")
    print("============================================================")
    try:
        test_execution_mode_values()
        test_validation_escalator()
        test_symbol_locator()
        print("============================================================")
        print("  ALL EXECUTION ROUTER CHECKS PASSED SUCCESSFULLY! [OK]")
        print("============================================================\n")
    except AssertionError as ae:
        print(f"  [FAIL] Assertion error: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"  [FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
