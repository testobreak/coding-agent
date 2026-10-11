# verify_patch_modes.py
import sys
import os
import json

# Setup sys path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".agent")))

from editing.patch_applier import PatchApplier
from editing.patch_engine import PatchEngine, PatchPlan, PatchOperation, PatchType, PatchSpan
from editing.ast_locator import ASTNodeInfo
from retrieval.hybrid_ranker import HybridRanker

class MockFileManager:
    def __init__(self, files=None):
        self.files = files or {}
    def read_file(self, path):
        return self.files.get(path, "")
    def write_file(self, path, content):
        self.files[path] = content

def test_span_patch():
    print("[Test] Verifying Mode 1: Span-based Patch...")
    applier = PatchApplier()
    content = "public class Calculator {\n    public int add(int a, int b) {\n        return a + b;\n    }\n}\n"
    # ASTNodeInfo for add method: start_byte=30, end_byte=78
    symbol_info = ASTNodeInfo(
        node_type="method",
        name="add",
        start_line=2,
        end_line=4,
        start_byte=30,
        end_byte=78,
        content="public int add(int a, int b) {\n        return a + b;\n    }"
    )
    
    # Apply full replacement of the symbol range
    patch = "public int add(int a, int b) {\n        return a + b + 10;\n    }"
    result = applier.apply_span_patch(content, patch, symbol_info)
    assert "return a + b + 10;" in result
    assert "public class Calculator" in result
    print("  [OK] Span patch successfully applied.")

def test_structural_patch():
    print("[Test] Verifying Mode 2: Structural Patch Helpers...")
    applier = PatchApplier()
    
    # 1. Test insert_import
    java_code = "package com.calc;\n\npublic class Calculator {}\n"
    res1 = applier.insert_import(java_code, "import org.slf4j.Logger;", "java")
    assert "import org.slf4j.Logger;" in res1
    assert res1.index("import ") > res1.index("package com.calc;")
    
    # Test duplicate import prevention
    res2 = applier.insert_import(res1, "import org.slf4j.Logger;", "java")
    assert res2.count("import org.slf4j.Logger;") == 1

    # 2. Test insert_class_member (Java)
    class_code = "public class Calculator {\n    private int x = 0;\n}"
    res3 = applier.insert_class_member(class_code, "Calculator", "public void reset() {\n    x = 0;\n}", "java")
    assert "public void reset() {" in res3
    assert res3.endswith("}")
    
    # 3. Test insert_class_member (Python)
    py_code = "class Calculator:\n    def __init__(self):\n        self.x = 0"
    res4 = applier.insert_class_member(py_code, "Calculator", "def reset(self):\n    self.x = 0", "python")
    assert "def reset(self):" in res4
    print("  [OK] Structural patch helpers verified.")

def test_full_rewrite():
    print("[Test] Verifying Mode 3: Full Rewrite...")
    file_mgr = MockFileManager({"calc.py": "def add(a, b):\n    return a + b"})
    engine = PatchEngine(file_mgr)
    
    op = PatchOperation(
        patch_type=PatchType.FULL_REWRITE,
        file="calc.py",
        start_line=1,
        end_line=1,
        content="# Completely new file\ndef run():\n    pass"
    )
    plan = PatchPlan(operations=[op])
    success = engine.apply_patch(plan)
    assert success
    assert "# Completely new file" in file_mgr.read_file("calc.py")
    print("  [OK] Full Rewrite successfully applied.")

def test_retrieval_boosting():
    print("[Test] Verifying Retrieval Exact Symbol Match Boosting...")
    ranker = HybridRanker()
    
    # Mock retrieval candidates
    candidates = [
        {
            "score": 0.5,
            "chunk": {
                "file": "services/EmployeeService.java",
                "symbol": "EmployeeService",
                "name": "EmployeeService",
                "content": "class EmployeeService {}"
            }
        },
        {
            "score": 0.6,
            "chunk": {
                "file": "specs/EmployeeSpecifications.java",
                "symbol": "EmployeeSpecifications",
                "name": "EmployeeSpecifications",
                "content": "class EmployeeSpecifications {}"
            }
        }
    ]
    
    # Query targets EmployeeService exactly
    query = "add logging to EmployeeService"
    ranked = ranker.rank(query, candidates)
    
    # EmployeeService should be ranked first because of the 4.0 points boost
    assert ranked[0]["chunk"]["symbol"] == "EmployeeService"
    # Its score should be boosted significantly (> 400.0)
    assert ranked[0]["score"] > 400.0
    print("  [OK] Retrieval symbol boosting verified.")

def main():
    print("============================================================")
    print("  Patch Engine Redesign & Retrieval Boosting Verification Suite")
    print("============================================================")
    try:
        test_span_patch()
        test_structural_patch()
        test_full_rewrite()
        test_retrieval_boosting()
        print("============================================================")
        print("  ALL PATCH ENGINE REDESIGN CHECKS PASSED SUCCESSFULLY! [OK]")
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
