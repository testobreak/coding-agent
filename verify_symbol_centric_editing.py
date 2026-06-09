# verify_symbol_centric_editing.py
#
# Verification suite for symbol-centric editing, AST replacements, and structured operations.

import sys
import os
import tempfile
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from editing.symbol_target import SymbolTarget
from editing.symbol_edit_request import SymbolEditRequest
from editing.ast_locator import ASTLocator, ASTNodeInfo
from editing.patch_applier import PatchApplier
from editing.patch import Patch
from planning.task_status import TaskStatus
from planning.task_types import TaskType
from editing.symbol_handle import SymbolHandle

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

class MockStateManager:
    def __init__(self):
        class MockState:
            def __init__(self):
                self.goal = "Test goal"
                self.status = "active"
                self.current_step = ""
                self.completed_steps = []
                self.failed_steps = []
                self.pending_executions = []
                self.current_plan = []
                self.test_failures = []
                self.repair_history = []
                self.retrieved_chunks = []
                self.active_symbols = []
                self.touched_files = []
                self.modification_targets = []
                self.modified_files = []
                self.generated_code = []
                self.reflections = []
                self.architecture_notes = []
                self.tool_outputs = []
                self.execution_history = []
                
                class MockRuntimeMemory:
                    total_iterations = 0
                    tool_call_count = 0
                    retrieval_count = 0
                    repair_count = 0
                    runtime_errors = []
                self.runtime_memory = MockRuntimeMemory()
                
        self.state = MockState()
        self.validations = 0
        self.modifications = 0

    def get_state(self):
        return self.state

    def increment_validations(self):
        self.validations += 1

    def increment_modifications(self):
        self.modifications += 1

    def add_tool_output(self, tool, result):
        pass

    def add_execution_record(self, record):
        pass

    def increment_tool_calls(self):
        pass

def test_models():
    print("[Test] Running SymbolTarget and SymbolEditRequest model tests...")
    
    # 1. SymbolTarget
    target = SymbolTarget(
        symbol_id="sym_1",
        qualified_name="EmployeeService.saveEmployee",
        symbol_type="method",
        file_path="src/EmployeeService.py",
        start_line=10,
        end_line=20,
        parent_symbol="EmployeeService"
    )
    d = target.to_dict()
    assert d["qualified_name"] == "EmployeeService.saveEmployee"
    assert d["parent_symbol"] == "EmployeeService"
    
    loaded = SymbolTarget.from_dict(d)
    assert loaded.symbol_id == "sym_1"
    assert loaded.start_line == 10
    
    # 2. SymbolEditRequest
    req = SymbolEditRequest(
        symbol_id="sym_1",
        qualified_name="EmployeeService.saveEmployee",
        current_source="def saveEmployee(): pass",
        goal="Add logging",
        dependencies=["Logger"]
    )
    rd = req.to_dict()
    assert rd["goal"] == "Add logging"
    assert rd["dependencies"] == ["Logger"]
    
    loaded_req = SymbolEditRequest.from_dict(rd)
    assert loaded_req.symbol_id == "sym_1"
    
    print("  [OK] Models verified successfully.")

def test_byte_level_replacement():
    print("[Test] Running byte-level surgical replacement tests...")
    
    # Sample python code
    sample_code = """class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "calc.py")
        Path(file_path).write_text(sample_code, encoding="utf-8")
        
        # Locate AST boundaries for add
        locator = ASTLocator()
        node_info = locator.find_symbol(file_path, "Calculator.add")
        assert node_info is not None, "Failed to locate Calculator.add symbol node in AST"
        assert "def add(self, a, b):" in node_info.content
        
        # SEARCH/REPLACE patch block targeting Calculator.add content
        patch_str = """<<<<<<< SEARCH
    def add(self, a, b):
        return a + b
=======
    def add(self, a, b):
        print("adding")
        return a + b
>>>>>>> REPLACE"""
        
        applier = PatchApplier()
        modified_content = applier.apply(sample_code, patch_str, node_info)
        
        # Verify that add was updated and subtract is completely untouched
        assert 'print("adding")' in modified_content
        assert "def subtract(self, a, b):" in modified_content
        assert "return a - b" in modified_content
        
        # Verify that line numbers are preserved for subtract
        original_lines = sample_code.splitlines()
        modified_lines = modified_content.splitlines()
        assert original_lines[-1] == modified_lines[-1]
        
    print("  [OK] Byte-level surgical replacement verified.")

def test_structured_operations():
    print("[Test] Running structured operations (modify, create, delete) tests...")
    from editing.symbol_editor import SymbolEditor
    
    sample_code = """class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        file_name = "calc.py"
        file_path = os.path.join(tmpdir, file_name)
        Path(file_path).write_text(sample_code, encoding="utf-8")
        
        file_mgr = MockFileManager(tmpdir)
        state_mgr = MockStateManager()
        
        # Setup mock dependencies
        class MockGit:
            def rollback_to_checkpoint(self, checkpoint): pass
        class MockTx:
            def __init__(self, *args, **kwargs):
                self.modified_files = []
            def begin(self): pass
            def commit(self): pass
            def rollback(self, reason=None): pass
            def save_to_db(self): pass
            
        import editing.symbol_editor
        editing.symbol_editor.EditTransaction = MockTx
        
        editor = SymbolEditor(
            file_manager=file_mgr,
            state_manager=state_mgr,
            git_manager=MockGit(),
            validator=type("V", (), {"validate_file_syntax": lambda *a: True})(),
            compile_validator=type("CV", (), {"validate": lambda *a: True})(),
            test_runner=type("T", (), {"run_backend_tests": lambda *a, **kw: {"success": True}})(),
            impact_analyzer=type("I", (), {"analyze": lambda *a: {}})(),
            retrieval_pipeline=type("RP", (), {"retriever": type("R", (), {"dependency_graph": None})()})()
        )
        
        # Monkeypatch resolver to return a SymbolHandle pointing to Calculator.subtract
        class MockResolver:
            def resolve(self, symbol_name, file_path=None):
                return [SymbolHandle("sym_calc_sub", symbol_name, "function", file_name, 5, 6)]
        editor.resolver = MockResolver()
        
        # 1. Test DELETE_SYMBOL
        res = editor.modify("Calculator.subtract", "", file_path=file_name, operation="delete_symbol")
        assert res["success"] is True
        
        updated_code = file_mgr.read_file(file_name)
        assert "def subtract(self, a, b):" not in updated_code, "subtract method was not deleted"
        assert "def add(self, a, b):" in updated_code, "add method was accidentally deleted"
        
        # 2. Test CREATE_SYMBOL
        # Target is Calculator class
        editor.resolver = type("MockR2", (), {"resolve": lambda *a, **kw: [SymbolHandle("sym_calc", "Calculator", "class", file_name, 1, 7)]})()
        
        # Mock LLM to return SEARCH/REPLACE block appending multiply method to Calculator class
        def mock_llm_chat(messages, role=None):
            return """<<<<<<< SEARCH
class Calculator:
    def add(self, a, b):
        return a + b
=======
class Calculator:
    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b
>>>>>>> REPLACE"""
        
        editor.patch_generator.llm.chat = mock_llm_chat
        
        res = editor.modify("Calculator", "Add multiply method", file_path=file_name, operation="create_symbol")
        print("CREATE_SYMBOL RESULT:", res)
        assert res["success"] is True
        
        final_code = file_mgr.read_file(file_name)
        assert "def multiply(self, a, b):" in final_code
        assert "def add(self, a, b):" in final_code
        
    print("  [OK] Structured operations verified.")

def run_all_tests():
    print("\n" + "=" * 60)
    print("  Symbol-Centric Editing Subsystem Tests")
    print("=" * 60)
    
    try:
        test_models()
        test_byte_level_replacement()
        test_structured_operations()
        print("\n" + "=" * 60)
        print("  ALL SYMBOL-CENTRIC EDITING TESTS PASSED SUCCESSFULLY! [OK]")
        print("=" * 60 + "\n")
    except AssertionError as ae:
        print(f"\n[FAIL] Assertion Failure: {ae}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
