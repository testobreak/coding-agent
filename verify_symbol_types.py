# verify_symbol_types.py
#
# Automated tests for decoupled symbol editing, SymbolHandle, SymbolResolver, Patch, and SymbolEditor.

import sys
import os
import subprocess
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

# Mock subprocess.run to prevent actual git commands during mock execution
def mock_subprocess_run(args, **kwargs):
    class MockCompletedProcess:
        def __init__(self):
            self.returncode = 0
            self.stdout = b"mock stdout"
            self.stderr = b""
    return MockCompletedProcess()

subprocess.run = mock_subprocess_run

from editing.symbol_handle import SymbolHandle
from editing.patch import Patch, PatchSet
from editing.symbol_resolver import SymbolResolver
from editing.symbol_editor import SymbolEditor

# Mock classes for testing
class MockResolvedSymbol:
    def __init__(self, name, file_path, symbol_type, start_line, end_line):
        self.name = name
        self.file_path = file_path
        self.symbol_type = symbol_type
        self.signature = f"public {symbol_type} {name}"
        self.start_line = start_line
        self.end_line = end_line

class MockContextResolver:
    def resolve(self, symbol_name, session=None):
        if symbol_name == "EmployeeService.saveEmployee":
            return [MockResolvedSymbol(
                name="saveEmployee",
                file_path="backend/src/main/java/com/hrms/employee/EmployeeService.java",
                symbol_type="method",
                start_line=10,
                end_line=25
            )]
        return []

class MockFileManager:
    def __init__(self):
        self.files = {}
        self.root = "/Users/ashish/Downloads/HRMS"

    def read_file(self, path):
        return self.files.get(path, "public class EmployeeService {\n    public void saveEmployee() {}\n}")

    def write_file(self, path, content):
        self.files[path] = content

    def resolve_path(self, path):
        return os.path.join(self.root, path)

class MockStateManager:
    def __init__(self):
        from memory.task_state import TaskState
        self.state = TaskState(goal="Mock edit")
        self.validations = 0
        self.modifications = 0

    def get_state(self):
        return self.state

    def increment_validations(self):
        self.validations += 1

    def increment_modifications(self):
        self.modifications += 1

class MockGitManager:
    def __init__(self):
        self.root = "/Users/ashish/Downloads/HRMS"
        self.committed = False
        self.rolled_back = False

    def get_last_checkpoint(self):
        return "mock_hash"

    def status(self):
        return "clean"

    def rollback_to_commit(self, commit):
        self.rolled_back = True

    def create_checkpoint(self, message):
        return "new_checkpoint"

    def restore_checkpoint(self, ref):
        self.rolled_back = True
        return True

class MockValidator:
    def __init__(self, fail_syntax=False):
        self.fail_syntax = fail_syntax

    def validate_file_syntax(self, path):
        if self.fail_syntax:
            raise ValueError("Syntax error simulated")

    def validate_retry(self, execution):
        pass

    def validate_execution(self, tool, args):
        pass

class MockCompileValidator:
    def validate(self, path):
        pass

class MockTestRunner:
    def run_backend_tests(self, test_filter=None):
        return {"success": True}

class MockLLM:
    def chat(self, messages, role=None):
        return """<<<<<<< SEARCH
    public void saveEmployee() {}
=======
    public void saveEmployee() {
        System.out.println("Log saving employee");
    }
>>>>>>> REPLACE"""

def test_symbol_resolver():
    print("[Test] Testing SymbolResolver handle resolution...")
    resolver = SymbolResolver()
    # Override the inner context resolver with our mock
    resolver._inner = MockContextResolver()
    
    handles = resolver.resolve("EmployeeService.saveEmployee")
    assert len(handles) == 1, "Expected 1 SymbolHandle resolved"
    handle = handles[0]
    
    assert isinstance(handle, SymbolHandle), "Expected SymbolHandle type"
    assert handle.fqn == "EmployeeService.saveEmployee"
    assert handle.kind == "method"
    assert handle.file_path == "backend/src/main/java/com/hrms/employee/EmployeeService.java"
    assert handle.start_line == 10
    assert handle.end_line == 25
    print("  [OK] SymbolResolver handles test passed.")

def test_symbol_editor_edit():
    print("[Test] Testing SymbolEditor.edit decoupled patch generation...")
    file_mgr = MockFileManager()
    state_mgr = MockStateManager()
    git_mgr = MockGitManager()
    val = MockValidator()
    comp_val = MockCompileValidator()
    tests = MockTestRunner()
    llm = MockLLM()
    
    editor = SymbolEditor(
        file_manager=file_mgr,
        state_manager=state_mgr,
        git_manager=git_mgr,
        validator=val,
        compile_validator=comp_val,
        test_runner=tests,
        impact_analyzer=None,
        retrieval_pipeline=None,
        llm=llm
    )
    
    handle = SymbolHandle(
        symbol_id="sym_1",
        fqn="EmployeeService.saveEmployee",
        kind="method",
        file_path="backend/src/main/java/com/hrms/employee/EmployeeService.java",
        start_line=2,
        end_line=3
    )
    
    patch = editor.edit(handle, "add logging")
    assert isinstance(patch, Patch), "Expected Patch object"
    assert patch.symbol_fqn == handle.fqn
    assert patch.file_path == handle.file_path
    assert "System.out.println" in patch.new_text, "Expected modified text inside patch"
    print("  [OK] SymbolEditor.edit test passed.")

def test_symbol_editor_apply_patch():
    print("[Test] Testing SymbolEditor.apply_patch validation and rollback...")
    file_mgr = MockFileManager()
    state_mgr = MockStateManager()
    git_mgr = MockGitManager()
    comp_val = MockCompileValidator()
    tests = MockTestRunner()
    
    # 1. Successful patch application
    val_success = MockValidator(fail_syntax=False)
    editor_success = SymbolEditor(
        file_manager=file_mgr,
        state_manager=state_mgr,
        git_manager=git_mgr,
        validator=val_success,
        compile_validator=comp_val,
        test_runner=tests,
        impact_analyzer=None,
        retrieval_pipeline=None
    )
    
    patch = Patch(
        symbol_fqn="EmployeeService.saveEmployee",
        file_path="backend/src/main/java/com/hrms/employee/EmployeeService.java",
        old_text="public void saveEmployee() {}",
        new_text="public class EmployeeService {\n    public void saveEmployee() {\n        System.out.println();\n    }\n}",
        patch_block="<<<<<<< SEARCH..."
    )
    
    res = editor_success.apply_patch(patch)
    assert res is True
    assert file_mgr.files[patch.file_path] == patch.new_text
    
    # 2. Rollback on syntax validation failure
    val_fail = MockValidator(fail_syntax=True)
    editor_fail = SymbolEditor(
        file_manager=file_mgr,
        state_manager=state_mgr,
        git_manager=git_mgr,
        validator=val_fail,
        compile_validator=comp_val,
        test_runner=tests,
        impact_analyzer=None,
        retrieval_pipeline=None
    )
    
    try:
        editor_fail.apply_patch(patch)
        assert False, "Should have raised exception on syntax error"
    except Exception as e:
        assert "Syntax error simulated" in str(e)
        assert git_mgr.rolled_back is True, "Expected Git rollback on failure"
        
    print("  [OK] SymbolEditor.apply_patch and rollback test passed.")

def run_all_tests():
    print("\n" + "=" * 60)
    print("  Decoupled Symbol Editing Subsystem Tests")
    print("=" * 60)
    try:
        test_symbol_resolver()
        test_symbol_editor_edit()
        test_symbol_editor_apply_patch()
        print("\n" + "=" * 60)
        print("  ALL DECOUPLED SYMBOL TESTS PASSED! [OK]")
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
