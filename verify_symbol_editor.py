import sys
import os
import uuid
import subprocess
from pathlib import Path
from dataclasses import dataclass

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from repository_intelligence.db.connection import SessionLocal
from editing.ast_locator import ASTLocator, ASTNodeInfo
from editing.patch_applier import PatchApplier
from editing.symbol_editor import SymbolEditor
from execution.executor import Executor


class MockStateManager:
    def __init__(self, task_id="mock_se_task_777"):
        self.task_id = task_id
        self.state = type("State", (), {
            "task_id": task_id,
            "modified_files": [],
            "generated_code": [],
            "goal": "mock_goal"
        })()
        self.validations_count = 0
        self.modifications_count = 0

    def get_state(self):
        return self.state

    def increment_validations(self):
        self.validations_count += 1

    def increment_modifications(self):
        self.modifications_count += 1

    def add_tool_output(self, tool, result):
        pass

    def add_execution_record(self, record):
        pass

    def increment_tool_calls(self):
        pass


class MockFileManager:
    def __init__(self, root):
        self.root = Path(root)

    def resolve_path(self, path):
        return str(self.root / path)

    def read_file(self, path):
        full_path = self.root / path
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return ""

    def write_file(self, path, content):
        full_path = self.root / path
        full_path.write_text(content, encoding="utf-8")
        return {"success": True}


def run_tests():
    print("\n" + "=" * 60)
    print("  SymbolEditor & AST-Backed Editing Integration Tests")
    print("=" * 60)

    repo_root = Path(__file__).resolve().parent

    # -------------------------------------------------------------
    # Test 1: ASTLocator for Python Symbols
    # -------------------------------------------------------------
    print("\n[Test 1] Testing ASTLocator finding Python class and function definitions...")
    locator = ASTLocator()
    
    py_code = """
class Calculator:
    def add(self, a, b):
        return a + b

def global_func():
    pass
"""
    py_file = repo_root / "temp_calculator.py"
    py_file.write_text(py_code, encoding="utf-8")

    try:
        # Locate Class Definition
        class_info = locator.find_symbol(str(py_file), "Calculator", py_code)
        assert class_info is not None, "Expected to locate Python class Calculator"
        assert class_info.node_type == "class_definition"
        assert class_info.start_line == 2
        assert "Calculator" in class_info.content
        print("  [OK] Successfully located Python class 'Calculator'.")

        # Locate Method Definition
        method_info = locator.find_symbol(str(py_file), "Calculator.add", py_code)
        assert method_info is not None, "Expected to locate Python method Calculator.add"
        assert method_info.node_type == "function_definition"
        assert method_info.start_line == 3
        assert "def add" in method_info.content
        print("  [OK] Successfully located Python method 'Calculator.add'.")

        # Locate Global Function
        func_info = locator.find_symbol(str(py_file), "global_func", py_code)
        assert func_info is not None, "Expected to locate Python global function global_func"
        assert func_info.node_type == "function_definition"
        assert func_info.start_line == 6
        print("  [OK] Successfully located Python global function 'global_func'.")

    finally:
        py_file.unlink(missing_ok=True)

    # -------------------------------------------------------------
    # Test 2: ASTLocator for Java Symbols
    # -------------------------------------------------------------
    print("\n[Test 2] Testing ASTLocator finding Java class and method declarations...")
    java_code = """package com.hrms.test;

public class EmployeeService {
    private double salary;

    public void raiseSalary(double amount) {
        this.salary += amount;
    }
}
"""
    java_file = repo_root / "temp_EmployeeService.java"
    java_file.write_text(java_code, encoding="utf-8")

    try:
        # Locate Class Declaration
        class_info = locator.find_symbol(str(java_file), "EmployeeService", java_code)
        assert class_info is not None, "Expected to locate Java class EmployeeService"
        assert class_info.node_type == "class_declaration"
        assert class_info.start_line == 3
        print("  [OK] Successfully located Java class 'EmployeeService'.")

        # Locate Method Declaration
        method_info = locator.find_symbol(str(java_file), "EmployeeService.raiseSalary", java_code)
        assert method_info is not None, "Expected to locate Java method raiseSalary"
        assert method_info.node_type == "method_declaration"
        assert method_info.start_line == 6
        assert "raiseSalary" in method_info.content
        print("  [OK] Successfully located Java method 'EmployeeService.raiseSalary'.")

    finally:
        java_file.unlink(missing_ok=True)

    # -------------------------------------------------------------
    # Test 3: PatchApplier SEARCH/REPLACE Block Handling
    # -------------------------------------------------------------
    print("\n[Test 3] Testing PatchApplier applying SEARCH/REPLACE overrides...")
    applier = PatchApplier()
    original_text = """line 1
line 2
target code block to replace
line 4
line 5"""

    patch = """<<<<<<< SEARCH
target code block to replace
=======
new updated code block
>>>>>>> REPLACE"""

    result = applier.apply(original_text, patch)
    assert "new updated code block" in result
    assert "target code block" not in result
    print("  [OK] Successfully applied SEARCH/REPLACE block replacement.")

    # -------------------------------------------------------------
    # Test 4: SymbolEditor coordinating transaction-safety and commit
    # -------------------------------------------------------------
    print("\n[Test 4] Testing SymbolEditor transaction coordination and validation safety...")
    
    # Write a dummy python file to edit
    target_file_rel = "temp_math_service.py"
    target_file_abs = repo_root / target_file_rel
    original_math_code = """class MathService:
    def compute(self, val):
        return val * 2
"""
    target_file_abs.write_text(original_math_code, encoding="utf-8")
    subprocess.run(["git", "add", target_file_rel], cwd=repo_root, capture_output=True)

    db_session = SessionLocal()
    task_id = f"test_se_task_{uuid.uuid4().hex[:6]}"

    try:
        file_mgr = MockFileManager(root=str(repo_root))
        state_mgr = MockStateManager(task_id=task_id)
        
        executor = Executor(file_manager=file_mgr, state_manager=state_mgr)

        # Monkeypatch ContextAssembler.build to avoid missing state attributes error
        from context.assembler import ContextAssembler
        ContextAssembler.build = lambda self, state: {"goal": getattr(state, "goal", "mock_goal"), "status": "active"}

        # Mock LLM chat to return Search/Replace block replacing compute method
        def mock_llm_chat(messages, role=None):
            return """<<<<<<< SEARCH
    def compute(self, val):
        return val * 2
=======
    def compute(self, val):
        print("computations started")
        return val * 3
>>>>>>> REPLACE"""
        executor.modifier.llm.chat = mock_llm_chat

        # Mock validators to pass successfully
        executor.validator.validate_file_syntax = lambda filepath: True
        executor.compile_validator.validate = lambda filepath: True
        executor.tests.run_backend_tests = lambda test_filter=None: {"success": True}

        # Run modify_symbol tool invocation
        result = executor.execute({
            "tool": "modify_symbol",
            "args": {
                "symbol": "MathService.compute",
                "path": target_file_rel,
                "goal": "Add print logging and change compute scalar"
            }
        })

        assert result["success"] is True, f"Expected execute to succeed, got: {result}"
        assert result["result"]["success"] is True, f"Expected modify_symbol result success to be True, got: {result['result']}"
        
        # Verify changes were committed to file on disk
        updated_code = target_file_abs.read_text(encoding="utf-8")
        assert "computations started" in updated_code, "Expected code changes to be committed"
        assert "val * 3" in updated_code, "Expected scalar multiplication modified"
        print("  [OK] SymbolEditor successfully compiled patch, ran validations, and committed changes.")

    finally:
        db_session.close()
        # Clean up target dummy file from git and filesystem
        subprocess.run(["git", "restore", target_file_rel], cwd=repo_root, capture_output=True)
        if target_file_abs.exists():
            target_file_abs.unlink(missing_ok=True)

    print("\n" + "=" * 60)
    print("  ALL AST-BACKED SYMBOL EDITOR TESTS PASSED! [OK]")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_tests()
