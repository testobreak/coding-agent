# verify_patch_engine.py
#
# Comprehensive verification script for Patch Engine v2 (drift-resistance,
# structured patch operations, transactional rollback) and IDE Bridge Integration.

import sys
import os
import tempfile
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from editing.patch_engine import PatchEngine, PatchPlan, PatchOperation, PatchType, PatchSpan
from editing.ast_locator import ASTLocator, ASTNodeInfo
from editing.patch_applier import PatchApplier
from editing.patch import Patch
from runtime.editor.models import RuntimeContext, EditorContext, Diagnostic
from context.context_builder import ContextBuilder
from routing.intent_router import IntentRouter, ExecutionMode

class MockFileManager:
    def __init__(self):
        self.files = {}

    def resolve_path(self, path):
        return path

    def read_file(self, path):
        return self.files.get(path)

    def write_file(self, path, content):
        self.files[path] = content
        return {"success": True}

class MockStateManager:
    def __init__(self, runtime_context=None):
        class MockState:
            def __init__(self, ctx):
                self.goal = "Fix the syntax error"
                self.status = "active"
                self.runtime_context = ctx or RuntimeContext()
                self.touched_files = []
                self.modified_files = []
                self.generated_code = []
                self.completed_steps = []
                self.failed_steps = []
                self.pending_executions = []
                self.current_plan = []
                self.test_failures = []
                self.repair_history = []
                self.retrieved_chunks = []
                self.active_symbols = []
                self.modification_targets = []
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
        
        self.state = MockState(runtime_context)

    def get_state(self):
        return self.state

def run_tests():
    print("\n" + "=" * 60)
    print("  Patch Engine v2 & IDE Bridge Verification Suite")
    print("=" * 60)

    # 1. Test Line Drift Resistance and AST Span Relocation
    print("\n[Test 1] Testing drift-resistant AST span relocation...")
    file_path = "math_service.py"
    original_code = """# Math Service
class MathService:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
"""
    file_mgr = MockFileManager()
    file_mgr.write_file(file_path, original_code)
    
    locator = ASTLocator()
    
    # Locate initial span
    initial_span = locator.find_symbol(file_path, "MathService.subtract", original_code)
    assert initial_span is not None, "Failed to locate initial symbol span"
    print(f"  Initial subtract method bounds: L{initial_span.start_line}-L{initial_span.end_line}")
    assert initial_span.start_line == 6, "Initial start line should be 6"

    # Simulate Line Drift: prepend 5 comments to the file
    drifted_code = "\n" * 5 + original_code
    file_mgr.write_file(file_path, drifted_code)

    # Relocate symbol on the live/drifted code
    relocated_span = locator.find_symbol(file_path, "MathService.subtract", drifted_code)
    assert relocated_span is not None, "Failed to relocate symbol span"
    print(f"  Relocated subtract method bounds (after line drift): L{relocated_span.start_line}-L{relocated_span.end_line}")
    assert relocated_span.start_line == 11, "Relocated start line should be 11 (6 + 5)"
    print("  [OK] Drift-resistant AST span relocation verified.")

    # 2. Test Structured Patch Operations
    print("\n[Test 2] Testing structured patch operations (insert_before, insert_after, replace, delete, rename)...")
    applier = PatchApplier()
    
    # 2a. replace
    rep_content = applier.apply_operation(original_code, "replace", "    def subtract(self, x, y):\n        return x - y", initial_span)
    assert "def subtract(self, x, y):" in rep_content, "Replace operation failed"
    print("  [OK] Structured replace operation verified.")

    # 2b. insert_before
    before_content = applier.apply_operation(original_code, "insert_before", "    # Subtract function", initial_span)
    assert "# Subtract function" in before_content and "def subtract" in before_content, "Insert before operation failed"
    print("  [OK] Structured insert_before operation verified.")

    # 2c. insert_after
    after_content = applier.apply_operation(original_code, "insert_after", "    # End of subtract", initial_span)
    assert "return a - b" in after_content and "# End of subtract" in after_content, "Insert after operation failed"
    print("  [OK] Structured insert_after operation verified.")

    # 2d. delete
    del_content = applier.apply_operation(original_code, "delete", "", initial_span)
    assert "def subtract" not in del_content, "Delete operation failed"
    print("  [OK] Structured delete operation verified.")

    # 2e. rename_symbol
    rename_content = applier.apply_operation(original_code, "rename_symbol", "minus", initial_span)
    assert "def minus(self, a, b):" in rename_content, "Rename operation failed"
    print("  [OK] Structured rename_symbol operation verified.")

    # 3. Test Transactional Rollback
    print("\n[Test 3] Testing PatchEngine multi-file transactional rollback on validation failure...")
    file_a = "service_a.py"
    file_b = "service_b.py"
    code_a = "def func_a():\n    return 1\n"
    code_b = "def func_b():\n    return 2\n"
    
    file_mgr.write_file(file_a, code_a)
    file_mgr.write_file(file_b, code_b)

    engine = PatchEngine(file_mgr)
    
    # Create patch plan containing edits in both files, but second file edit will introduce a syntax error
    op_a = PatchOperation(
        patch_type=PatchType.REPLACE,
        file=file_a,
        start_line=1,
        end_line=2,
        content="def func_a():\n    return 100\n"
    )
    
    # Introduce syntax error: missing colon
    op_b = PatchOperation(
        patch_type=PatchType.REPLACE,
        file=file_b,
        start_line=1,
        end_line=2,
        content="def func_b()\n    return 200\n"
    )
    
    plan = PatchPlan(operations=[op_a, op_b])
    
    success = engine.apply_patch(plan)
    assert not success, "Patch application should fail due to syntax error in service_b.py"
    
    # Verify rollback: both files must be at their original state
    assert file_mgr.read_file(file_a) == code_a, "service_a.py was not rolled back"
    assert file_mgr.read_file(file_b) == code_b, "service_b.py was not rolled back"
    print("  [OK] Multi-file transactional rollback successfully restored original contents.")

    # 4. Test IDE Bridge Context Builder Integration
    print("\n[Test 4] Testing ContextBuilder IDE state integration (Layer 0)...")
    
    class MockRetrievalPipeline:
        def retrieve_relevant_chunks(self, query, top_k=10, expand_context=True, goal=None):
            return []
            
    pipeline = MockRetrievalPipeline()
    
    diag = Diagnostic(
        file="math_service.py",
        line=3,
        severity="error",
        message="Undefined variable 'x'",
        source="pyflake"
    )
    ctx = RuntimeContext(
        active_file="math_service.py",
        cursor_position=(3, 5),
        selection="def add(self, a, b):",
        selection_range=((3, 5), (3, 25)),
        diagnostics=[diag],
        unsaved_buffer="def custom_math():\n    pass\n"
    )
    
    state_mgr = MockStateManager(ctx)
    builder = ContextBuilder(pipeline)
    
    # Force assist mode (Layer 0 + 1)
    from context.policy_engine import ContextPolicy, ContextPolicyEngine
    policy = ContextPolicy(
        include_ui_context=True,
        include_local_symbol=True,
        include_repo_context=False,
        include_memory=False,
        token_budget=10000
    )
    
    # Assemble planning context
    pkg = builder.build_planning_context("fix undefined variable x", state_mgr.get_state(), policy=policy)
    
    # Verify diagnostics and selection snippets are present and prioritized
    snippet_symbols = [s.symbol for s in pkg.snippets]
    print(f"  Generated snippet symbols: {snippet_symbols}")
    
    assert any("active_diagnostic" in s for s in snippet_symbols), "Active diagnostic snippet missing"
    assert any("active_selection" in s for s in snippet_symbols), "Active selection snippet missing"
    assert any("active_file_focus" in s for s in snippet_symbols), "Active file focus snippet missing"
    
    # Verify that the unsaved buffer was used to generate focus code instead of file on disk
    focus_snippets = [s for s in pkg.snippets if "active_file_focus" in s.symbol]
    assert len(focus_snippets) > 0, "Missing active file focus snippet"
    assert "custom_math" in focus_snippets[0].source, "Unsaved buffer was not utilized for focus snippet"
    print("  [OK] ContextBuilder successfully prioritized diagnostics, selection range, and unsaved buffers.")

    # 5. Test IntentRouter Editor Context integration
    print("\n[Test 5] Testing IntentRouter diagnostic and selection aware routing...")
    decision_diag = IntentRouter.route("fix this syntax issue", ctx)
    print(f"  Decision with diagnostics: mode={decision_diag.mode.value}, confidence={decision_diag.confidence}, reason='{decision_diag.reason}'")
    assert decision_diag.mode == ExecutionMode.SMART_EDIT, "Should route to SMART_EDIT due to local diagnostics"

    ctx_no_selection = RuntimeContext(
        active_file="math_service.py",
        cursor_position=(3, 5),
        selection=None,
        selection_range=None,
        diagnostics=[],
        unsaved_buffer=""
    )
    decision_normal = IntentRouter.route("explain how this function works", ctx_no_selection)
    print(f"  Decision with assist: mode={decision_normal.mode.value}, confidence={decision_normal.confidence}")
    assert decision_normal.mode == ExecutionMode.CODE_ASSIST, "Should route to CODE_ASSIST"
    print("  [OK] IntentRouter routing decisions verified.")

    print("\n" + "=" * 60)
    print("  ALL PATCH ENGINE V2 & IDE BRIDGE TESTS PASSED! [OK]")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_tests()
