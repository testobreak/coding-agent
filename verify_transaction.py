import sys
import os
import uuid
import subprocess
from pathlib import Path
from sqlalchemy import text

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from repository_intelligence.db.connection import SessionLocal
from repository.git_manager import GitManager
from execution.modification_transaction import ModificationTransaction
from execution.executor import Executor


class MockStateManager:
    """Mock state manager for test state isolation."""
    def __init__(self, task_id="mock_tx_task_999"):
        self.task_id = task_id
        self.state = type("State", (), {
            "task_id": task_id,
            "modified_files": [],
            "generated_code": []
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
    """Mock file manager targeting local workspace root."""
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


def clean_db_checkpoints(session, task_id):
    """Utility to clean up records under target task_id."""
    try:
        session.execute(
            text("DELETE FROM modification_checkpoints WHERE task_id = :task_id"),
            {"task_id": task_id}
        )
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Warning during DB cleanup: {e}")


def run_tests():
    print("\n" + "=" * 60)
    print("  ModificationTransaction & Multi-Level Validation Tests")
    print("=" * 60)

    from repository_intelligence.db.connection import Base, engine
    Base.metadata.create_all(bind=engine)

    # Monkeypatch ContextAssembler.build to avoid missing state attributes error in tests
    from context.assembler import ContextAssembler
    ContextAssembler.build = lambda self, state: {"goal": getattr(state, "goal", "Verify Rollback"), "status": "active"}

    db_session = SessionLocal()
    task_id = f"test_task_{uuid.uuid4().hex[:6]}"
    
    # 1. Setup targeted dummy files in repo root
    repo_root = Path(__file__).resolve().parent
    target_file_rel = "targeted_file.txt"
    target_file_abs = repo_root / target_file_rel
    
    # Write initial state
    original_text = "original content base"
    target_file_abs.write_text(original_text, encoding="utf-8")
    
    # Ensure git tracks the file
    subprocess.run(["git", "add", target_file_rel], cwd=repo_root, capture_output=True)

    try:
        # Pre-cleanup
        clean_db_checkpoints(db_session, task_id)

        git_mgr = GitManager(root=str(repo_root))
        state_mgr = MockStateManager(task_id=task_id)

        # -------------------------------------------------------------
        # Test 1: Direct Transaction Begin & Rollback with Dirty State
        # -------------------------------------------------------------
        print("\n[Test 1] Testing direct ModificationTransaction Rollback...")
        
        tx = ModificationTransaction(git_manager=git_mgr, state_manager=state_mgr, goal="Verify Rollback")
        tx.begin()

        # Check DB has PENDING record
        row = db_session.execute(
            text("SELECT validation_status, goal FROM modification_checkpoints WHERE id = :id"),
            {"id": tx.checkpoint_id}
        ).fetchone()
        assert row is not None, "Transaction record not found in DB"
        assert row[0] == "PENDING", f"Expected PENDING status, got {row[0]}"
        assert row[1] == "Verify Rollback", f"Expected matching goal, got {row[1]}"
        print("  [OK] Initial transaction logged as PENDING in PostgreSQL.")

        # Modify target file
        target_file_abs.write_text("corrupted content during transaction", encoding="utf-8")

        # Rollback
        tx.rollback(reason="Simulated syntax validation failure")

        # Verify file is restored
        current_text = target_file_abs.read_text(encoding="utf-8")
        assert current_text == original_text, f"Expected file restored to '{original_text}', got '{current_text}'"
        print("  [OK] File successfully reverted to original state upon rollback.")

        # Verify DB status updated to ROLLED_BACK
        row = db_session.execute(
            text("SELECT validation_status, rollback_reason FROM modification_checkpoints WHERE id = :id"),
            {"id": tx.checkpoint_id}
        ).fetchone()
        assert row[0] == "ROLLED_BACK", f"Expected ROLLED_BACK status, got {row[0]}"
        assert "Simulated syntax validation failure" in row[1], f"Expected matching reason, got {row[1]}"
        print("  [OK] Transaction logged as ROLLED_BACK with failure reason in PostgreSQL.")

        # -------------------------------------------------------------
        # Test 2: Direct Transaction Begin & Commit
        # -------------------------------------------------------------
        print("\n[Test 2] Testing direct ModificationTransaction Commit...")
        
        tx = ModificationTransaction(git_manager=git_mgr, state_manager=state_mgr, goal="Verify Commit")
        tx.begin()

        # Modify target file
        committed_text = "successfully committed modification content"
        target_file_abs.write_text(committed_text, encoding="utf-8")
        tx.modified_files.append(target_file_rel)

        # Commit
        tx.commit()

        # Verify file changes are kept
        current_text = target_file_abs.read_text(encoding="utf-8")
        assert current_text == committed_text, f"Expected file kept at '{committed_text}', got '{current_text}'"
        print("  [OK] File modifications successfully persisted on commit.")

        # Verify DB status updated to COMMITTED
        row = db_session.execute(
            text("SELECT validation_status, modified_files FROM modification_checkpoints WHERE id = :id"),
            {"id": tx.checkpoint_id}
        ).fetchone()
        assert row[0] == "COMMITTED", f"Expected COMMITTED status, got {row[0]}"
        assert target_file_rel in row[1], f"Expected modified files tracked in DB, got {row[1]}"
        print("  [OK] Transaction logged as COMMITTED in PostgreSQL.")

        # Reset file back to original for subsequent tests
        target_file_abs.write_text(original_text, encoding="utf-8")

        # -------------------------------------------------------------
        # Test 3: Executor modify_symbol Syntax Validation Rollback
        # -------------------------------------------------------------
        print("\n[Test 3] Testing Executor modify_symbol Rollback on Syntax Failure...")
        
        file_mgr = MockFileManager(root=str(repo_root))
        executor = Executor(file_manager=file_mgr, state_manager=state_mgr)

        # Mock LLM chat to return Search/Replace block
        def mock_llm_chat(messages, role=None):
            user_msg = messages[-1]["content"]
            if "syntax failure" in user_msg or "Introduce syntax failure" in user_msg:
                return """<<<<<<< SEARCH
original content base
=======
invalid syntax content
>>>>>>> REPLACE"""
            elif "compilation failure" in user_msg or "Introduce compilation failure" in user_msg:
                return """<<<<<<< SEARCH
original content base
=======
compilation failure content
>>>>>>> REPLACE"""
            elif "test suite failure" in user_msg or "Introduce test suite failure" in user_msg:
                return """<<<<<<< SEARCH
original content base
=======
test failure content
>>>>>>> REPLACE"""
            return """<<<<<<< SEARCH
original content base
=======
modified content base
>>>>>>> REPLACE"""
        executor.modifier.llm.chat = mock_llm_chat

        # Monkeypatch validator to raise a syntax error
        def mock_validate_syntax(filepath):
            raise SyntaxError("Invalid bracing / parentheses matching error")
        executor.validator.validate_file_syntax = mock_validate_syntax

        result = executor.execute({
            "tool": "modify_symbol",
            "args": {
                "symbol": "dummy_symbol",
                "path": target_file_rel,
                "goal": "Introduce syntax failure"
            }
        })

        assert result["result"]["success"] is False, f"Expected modify_symbol result success to be False, got: {result}"
        assert "Syntax validation failed" in result["result"]["error"], f"Expected syntax error, got: {result['result']['error']}"
        
        # Verify repo rolled back
        current_text = target_file_abs.read_text(encoding="utf-8")
        assert current_text == original_text, f"Expected rollback to '{original_text}', got '{current_text}'"
        print("  [OK] Executor automatically rolled back file changes on Syntax Validation Failure.")

        # Verify DB checkpoint
        row = db_session.execute(
            text("""
                SELECT validation_status, rollback_reason 
                FROM modification_checkpoints 
                WHERE task_id = :task_id AND goal = 'Modify symbol dummy_symbol in targeted_file.txt'
            """),
            {"task_id": task_id}
        ).fetchone()
        assert row is not None, "Expected database checkpoint recorded"
        assert row[0] == "ROLLED_BACK", f"Expected ROLLED_BACK, got {row[0]}"
        assert "Syntax validation failed" in row[1], f"Expected matching reason, got {row[1]}"
        print("  [OK] Syntax failure transaction logged as ROLLED_BACK in PostgreSQL.")

        # -------------------------------------------------------------
        # Test 4: Executor modify_symbol Compile Validation Rollback
        # -------------------------------------------------------------
        print("\n[Test 4] Testing Executor modify_symbol Rollback on Compilation Failure...")

        # Reset validators
        executor.validator.validate_file_syntax = lambda filepath: True

        # Monkeypatch compile_validator to raise a compilation error
        def mock_validate_compile(filepath):
            raise RuntimeError("Symbol resolution or import mismatch compilation error")
        executor.compile_validator.validate = mock_validate_compile

        result = executor.execute({
            "tool": "modify_symbol",
            "args": {
                "symbol": "dummy_symbol",
                "path": target_file_rel,
                "goal": "Introduce compilation failure"
            }
        })

        assert result["result"]["success"] is False, f"Expected modify_symbol result success to be False, got: {result}"
        assert "Compilation validation failed" in result["result"]["error"], f"Expected compilation error, got: {result['result']['error']}"

        # Verify repo rolled back
        current_text = target_file_abs.read_text(encoding="utf-8")
        assert current_text == original_text, f"Expected rollback to '{original_text}', got '{current_text}'"
        print("  [OK] Executor automatically rolled back file changes on Compilation Validation Failure.")

        # Verify DB checkpoint
        row = db_session.execute(
            text("""
                SELECT validation_status, rollback_reason 
                FROM modification_checkpoints 
                WHERE task_id = :task_id AND goal = 'Modify symbol dummy_symbol in targeted_file.txt'
            """),
            {"task_id": task_id}
        ).fetchall()
        compilation_row = None
        for r in row:
            if r[1] and "Compilation validation failed" in r[1]:
                compilation_row = r
                break
        assert compilation_row is not None, "Expected database checkpoint for compilation failure recorded"
        assert compilation_row[0] == "ROLLED_BACK", f"Expected ROLLED_BACK, got {compilation_row[0]}"
        print("  [OK] Compilation failure transaction logged as ROLLED_BACK in PostgreSQL.")

        # -------------------------------------------------------------
        # Test 5: Executor modify_symbol Test Suite Failure Rollback
        # -------------------------------------------------------------
        print("\n[Test 5] Testing Executor modify_symbol Rollback on Test Suite Failure...")

        # Reset compile validator
        executor.compile_validator.validate = lambda filepath: True

        # Monkeypatch tests to return a failure status
        def mock_run_backend_tests(test_filter=None):
            return {
                "success": False,
                "failures": [
                    {
                        "error_type": "AssertionError",
                        "message": "Expected salary to equal 5000, got 4500",
                        "likely_source_files": [target_file_rel]
                    }
                ]
            }
        executor.tests.run_backend_tests = mock_run_backend_tests

        result = executor.execute({
            "tool": "modify_symbol",
            "args": {
                "symbol": "dummy_symbol",
                "path": target_file_rel,
                "goal": "Introduce test suite failure"
            }
        })

        assert result["result"]["success"] is False, f"Expected modify_symbol result success to be False, got: {result}"
        assert "Test suite validation failed" in result["result"]["error"], f"Expected test error, got: {result['result']['error']}"

        # Verify repo rolled back
        current_text = target_file_abs.read_text(encoding="utf-8")
        assert current_text == original_text, f"Expected rollback to '{original_text}', got '{current_text}'"
        print("  [OK] Executor automatically rolled back file changes on Test Suite Validation Failure.")

        # Verify DB checkpoint
        row = db_session.execute(
            text("""
                SELECT validation_status, rollback_reason 
                FROM modification_checkpoints 
                WHERE task_id = :task_id AND goal = 'Modify symbol dummy_symbol in targeted_file.txt'
            """),
            {"task_id": task_id}
        ).fetchall()
        test_row = None
        for r in row:
            if r[1] and "Test suite validation failed" in r[1]:
                test_row = r
                break
        assert test_row is not None, "Expected database checkpoint for test suite failure recorded"
        assert test_row[0] == "ROLLED_BACK", f"Expected ROLLED_BACK, got {test_row[0]}"
        print("  [OK] Test suite failure transaction logged as ROLLED_BACK in PostgreSQL.")

        print("\n" + "=" * 60)
        print("  ALL TRANSACTION MANAGER & VALIDATION TESTS PASSED! [OK]")
        print("=" * 60 + "\n")

    except AssertionError as ae:
        print(f"\n[FAIL] ASSERTION ERROR: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Final cleanup
        clean_db_checkpoints(db_session, task_id)
        db_session.close()
        
        # Remove target dummy file from git and filesystem
        subprocess.run(["git", "restore", target_file_rel], cwd=repo_root, capture_output=True)
        if target_file_abs.exists():
            target_file_abs.unlink(missing_ok=True)


if __name__ == "__main__":
    run_tests()
