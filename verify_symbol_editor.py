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

    # -------------------------------------------------------------
    # Test 5: ASTLocator for TypeScript/JavaScript Symbols
    # -------------------------------------------------------------
    print("\n[Test 5] Testing ASTLocator finding TypeScript class, method, and function declarations...")
    ts_code = """
class UserService {
    private users: string[] = [];

    public addUser(name: string): void {
        this.users.push(name);
    }
}

function globalHelper() {
    return 42;
}
"""
    ts_file = repo_root / "temp_UserService.ts"
    ts_file.write_text(ts_code, encoding="utf-8")

    try:
        # Locate Class
        class_info = locator.find_symbol(str(ts_file), "UserService", ts_code)
        assert class_info is not None, "Expected to locate TypeScript class UserService"
        assert class_info.node_type == "class_declaration"
        assert class_info.start_line == 2
        print("  [OK] Successfully located TypeScript class 'UserService'.")

        # Locate Method
        method_info = locator.find_symbol(str(ts_file), "UserService.addUser", ts_code)
        assert method_info is not None, "Expected to locate TypeScript method UserService.addUser"
        assert method_info.node_type == "method_definition"
        assert method_info.start_line == 5
        print("  [OK] Successfully located TypeScript method 'UserService.addUser'.")

        # Locate Global Function
        func_info = locator.find_symbol(str(ts_file), "globalHelper", ts_code)
        assert func_info is not None, "Expected to locate TypeScript global function globalHelper"
        assert func_info.node_type == "function_declaration"
        assert func_info.start_line == 10
        print("  [OK] Successfully located TypeScript global function 'globalHelper'.")

    finally:
        ts_file.unlink(missing_ok=True)

    # -------------------------------------------------------------
    # Test 6: SymbolResolutionError on Unresolved Symbols
    # -------------------------------------------------------------
    print("\n[Test 6] Testing SymbolResolver raising SymbolResolutionError on unresolved symbols...")
    from editing.symbol_resolver import SymbolResolver, SymbolResolutionError
    resolver = SymbolResolver()
    
    # Create a dummy file that exists
    dummy_file = repo_root / "temp_dummy_service.py"
    dummy_file.write_text("class DummyService:\n    pass\n", encoding="utf-8")
    
    try:
        # Resolving a non-existent symbol in the file should raise SymbolResolutionError
        try:
            resolver.resolve("DummyService.non_existent_method", file_path=str(dummy_file), allow_fallback=False)
            assert False, "Expected SymbolResolutionError to be raised"
        except SymbolResolutionError as e:
            print(f"  [OK] Successfully caught expected SymbolResolutionError: {e}")
            
        # Resolving with allow_fallback=True should fallback instead of raising
        fallback_handles = resolver.resolve("DummyService.non_existent_method", file_path=str(dummy_file), allow_fallback=True)
        assert len(fallback_handles) == 1, "Expected 1 fallback handle"
        assert fallback_handles[0].kind == "fallback", f"Expected kind to be fallback, got {fallback_handles[0].kind}"
        print("  [OK] Successfully verified fallback allowed option.")
        
    finally:
        dummy_file.unlink(missing_ok=True)

    # -------------------------------------------------------------
    # Test 7: SymbolResolver fallback behavior based on execution mode
    # -------------------------------------------------------------
    print("\n[Test 7] Testing SymbolResolver fallback restriction based on execution mode...")
    from memory.state_manager import StateManager
    
    # Create a dummy file that exists
    dummy_file = repo_root / "temp_dummy_service_2.py"
    dummy_file.write_text("class DummyService2:\n    pass\n", encoding="utf-8")
    
    try:
        # Scenario A: PATCH Mode (goal routes to PATCH) -> fallback should be forbidden
        patch_state_mgr = StateManager()
        patch_state_mgr.create_task(goal="update salary", task_id="test_task_patch")
        
        resolver_patch = SymbolResolver(state_manager=patch_state_mgr)
        
        try:
            resolver_patch.resolve(
                "DummyService2.non_existent_method", 
                file_path=str(dummy_file), 
                allow_fallback=True
            )
            assert False, "Expected SymbolResolutionError to be raised in PATCH mode even when allow_fallback=True"
        except SymbolResolutionError as e:
            print(f"  [OK] Successfully caught expected SymbolResolutionError in PATCH mode: {e}")
            
        # Scenario B: AGENT Mode (goal routes to AGENT) -> fallback should be allowed
        agent_state_mgr = StateManager()
        agent_state_mgr.create_task(goal="complex request", task_id="test_task_agent")
        
        resolver_agent = SymbolResolver(state_manager=agent_state_mgr)
        
        fallback_handles = resolver_agent.resolve(
            "DummyService2.non_existent_method", 
            file_path=str(dummy_file), 
            allow_fallback=True
        )
        assert len(fallback_handles) == 1, "Expected 1 fallback handle in AGENT mode"
        assert fallback_handles[0].kind == "fallback", f"Expected fallback handle, got {fallback_handles[0].kind}"
        print("  [OK] Successfully verified fallback allowed in AGENT mode.")
        
    finally:
        dummy_file.unlink(missing_ok=True)

    # -------------------------------------------------------------
    # Test 8: JavaAdapter AST surgical boundaries verification
    # -------------------------------------------------------------
    print("\n[Test 8] Testing JavaAdapter AST surgical boundaries with JavaParser...")
    from editing.language_adapter import JavaAdapter
    from editing.models.edit_plan import ReplaceMethodBody
    from editing.symbol_handle import SymbolHandle
    
    java_code = """package com.example.service;
public class EmployeeService {
    public void raiseSalary(Employee emp, double percentage) {
        double current = emp.getSalary();
        emp.setSalary(current * (1 + percentage));
    }
    
    public EmployeeService() {
        // constructor
    }
}
"""
    # Create temp java file
    java_file = repo_root / "TempEmployeeService.java"
    java_file.write_text(java_code, encoding="utf-8")
    
    try:
        adapter = JavaAdapter()
        plan = ReplaceMethodBody(
            symbol="EmployeeService.raiseSalary",
            goal="update method body",
        )
        symbol_handle = SymbolHandle(
            symbol_id="sym_raiseSalary",
            fqn="EmployeeService.raiseSalary",
            kind="method",
            file_path=str(java_file),
            start_line=3,
            end_line=6
        )
        
        # Build patch (uses JavaParser under the hood to locate boundaries)
        patch = adapter.build_patch(
            plan=plan,
            symbol=symbol_handle,
            original_content=java_code
        )
        
        # Verify the patch old_text is exactly the raiseSalary method block!
        assert "public void raiseSalary" in patch.old_text, "Expected raiseSalary signature in old_text"
        assert "emp.setSalary" in patch.old_text, "Expected method body in old_text"
        assert "public EmployeeService()" not in patch.old_text, "Expected constructor to not be in old_text"
        print("  [OK] Successfully verified raiseSalary method AST boundaries.")
        
        # Now let's try matching the constructor
        constructor_handle = SymbolHandle(
            symbol_id="sym_constructor",
            fqn="EmployeeService.EmployeeService",
            kind="constructor",
            file_path=str(java_file),
            start_line=8,
            end_line=10
        )
        patch_constructor = adapter.build_patch(
            plan=plan,
            symbol=constructor_handle,
            original_content=java_code
        )
        assert "public EmployeeService()" in patch_constructor.old_text, "Expected constructor in old_text"
        assert "raiseSalary" not in patch_constructor.old_text, "Expected raiseSalary to not be in constructor old_text"
        print("  [OK] Successfully verified constructor AST boundaries.")
        
    finally:
        java_file.unlink(missing_ok=True)

    # -------------------------------------------------------------
    # Test 9: TypeScriptAdapter AST surgical boundaries verification
    # -------------------------------------------------------------
    print("\n[Test 9] Testing TypeScriptAdapter AST surgical boundaries with TypeScriptParser...")
    from editing.language_adapter import TypeScriptAdapter
    from editing.models.edit_plan import ReplaceMethodBody
    from editing.symbol_handle import SymbolHandle
    
    ts_code = """import React from 'react';
export interface User {
    id: string;
    name: string;
}

export class UserService {
    public getUser(id: string): User {
        return { id, name: 'John Doe' };
    }
}

export const useUser = (id: string) => {
    return { user: { id, name: 'Hook User' } };
};
"""
    # Create temp typescript file
    ts_file = repo_root / "TempUserService.tsx"
    ts_file.write_text(ts_code, encoding="utf-8")
    
    try:
        adapter = TypeScriptAdapter()
        plan = ReplaceMethodBody(
            symbol="UserService.getUser",
            goal="update getUser method",
        )
        symbol_handle = SymbolHandle(
            symbol_id="sym_getUser",
            fqn="UserService.getUser",
            kind="method",
            file_path=str(ts_file),
            start_line=8,
            end_line=10
        )
        
        # Build patch
        patch = adapter.build_patch(
            plan=plan,
            symbol=symbol_handle,
            original_content=ts_code
        )
        
        # Verify the patch old_text is exactly the getUser method block!
        assert "getUser(id: string)" in patch.old_text, "Expected getUser signature in old_text"
        assert "John Doe" in patch.old_text, "Expected method body in old_text"
        assert "export const useUser" not in patch.old_text, "Expected hook to not be in old_text"
        print("  [OK] Successfully verified getUser method AST boundaries.")
        
        # Now try matching the arrow function hook
        hook_handle = SymbolHandle(
            symbol_id="sym_useUser",
            fqn="useUser",
            kind="function",
            file_path=str(ts_file),
            start_line=13,
            end_line=15
        )
        patch_hook = adapter.build_patch(
            plan=plan,
            symbol=hook_handle,
            original_content=ts_code
        )
        assert "export const useUser = " in patch_hook.old_text, "Expected arrow function declaration in old_text"
        assert "Hook User" in patch_hook.old_text, "Expected arrow function body in old_text"
        assert "getUser" not in patch_hook.old_text, "Expected method to not be in arrow function old_text"
        print("  [OK] Successfully verified arrow function hook AST boundaries.")
        
    finally:
        ts_file.unlink(missing_ok=True)

    print("\n" + "=" * 60)
    print("  ALL AST-BACKED SYMBOL EDITOR TESTS PASSED! [OK]")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_tests()
