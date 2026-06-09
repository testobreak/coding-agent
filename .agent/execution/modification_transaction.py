# execution/modification_transaction.py
#
# Enterprise-grade Git-backed Multi-Stage Modification Transaction & Rollback Manager.
# Treats every repository modification as a transaction.
# Logs metadata to PostgreSQL table `modification_checkpoints`.
#

import uuid
import subprocess
from datetime import datetime
from typing import List, Optional
from sqlalchemy import text
from repository_intelligence.db.connection import SessionLocal


class ModificationTransaction:

    def __init__(
        self,
        git_manager,
        state_manager,
        goal: str = ""
    ):
        self.git = git_manager
        self.state_manager = state_manager
        self.goal = goal
        
        # Resolve task_id safely from state
        state = getattr(state_manager, "get_state", lambda: None)()
        self.task_id = getattr(state, "task_id", "unknown_task") if state else "unknown_task"
        if not self.task_id:
            self.task_id = "unknown_task"
            
        self.checkpoint_id = None
        self.stash_ref = None
        self.created_at = None
        self.modified_files = []
        self.validation_status = "PENDING"
        self.rollback_reason = None
        self.ensure_tables()

    def ensure_tables(self) -> None:
        """
        Ensures the modification_checkpoints table exists in the database.
        """
        session = SessionLocal()
        try:
            sql = """
                CREATE TABLE IF NOT EXISTS modification_checkpoints (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    goal TEXT,
                    modified_files TEXT[],
                    validation_status TEXT NOT NULL,
                    rollback_reason TEXT
                );
            """
            if "sqlite" in str(session.bind.url):
                sql = sql.replace("TEXT[]", "TEXT")
            session.execute(text(sql))
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ModificationTransaction] Warning: Failed to ensure checkpoints table: {e}")
        finally:
            session.close()

    def begin(self) -> Optional[str]:
        """
        Begins the transaction. Creates a git stash checkpoint if changes exist.
        Logs the initial checkpoint entry in PostgreSQL.
        """
        self.checkpoint_id = f"tx_checkpoint_{uuid.uuid4().hex[:8]}"
        self.created_at = datetime.utcnow()
        self.modified_files = []
        self.validation_status = "PENDING"
        self.rollback_reason = None

        print(f"[ModificationTransaction] [OK] Beginning transaction {self.checkpoint_id}")

        # Call GitManager to stash pre-transaction dirty/untracked changes
        self.stash_ref = self.git.create_checkpoint(f"tx_checkpoint_{self.checkpoint_id}")
        
        if self.stash_ref:
            print(f"[ModificationTransaction] Snapshot saved under stash reference: {self.stash_ref}")
        else:
            print("[ModificationTransaction] No existing local changes to stash. Clean workspace checkpoint initialized.")

        self.save_to_db()
        return self.checkpoint_id

    def commit(self) -> bool:
        """
        Commits the transaction. Drops the stashed pre-transaction snapshot
        since changes are accepted and completed.
        """
        self.validation_status = "COMMITTED"
        print(f"[ModificationTransaction] [OK] Committing transaction {self.checkpoint_id}")

        if self.stash_ref:
            try:
                # Discard stash entry cleanly as it is no longer required
                subprocess.run(
                    ["git", "stash", "drop", self.stash_ref],
                    cwd=self.git.root,
                    capture_output=True,
                    check=True
                )
                print(f"[ModificationTransaction] Discarded stash reference: {self.stash_ref}")
            except Exception as e:
                print(f"[ModificationTransaction] Warning: Failed to drop stash {self.stash_ref}: {e}")

        self.save_to_db()
        return True

    def rollback(self, reason: str = None) -> bool:
        """
        Rolls back all changes made during the transaction.
        Reverts working directory via hard reset + clean and restores the stash snapshot.
        """
        self.validation_status = "ROLLED_BACK"
        self.rollback_reason = reason
        print(f"[ModificationTransaction] [FAIL] Rolling back transaction {self.checkpoint_id}. Reason: {reason}")

        try:
            # Discard any newly made changes in working directory (tracked and untracked)
            subprocess.run(
                ["git", "reset", "--hard"],
                cwd=self.git.root,
                capture_output=True,
                check=True
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=self.git.root,
                capture_output=True,
                check=True
            )
            print("[ModificationTransaction] Hard reset and untracked file cleaning complete.")

            # Restore original snapshot if one was created
            if self.stash_ref:
                restored = self.git.restore_checkpoint(self.stash_ref)
                if restored:
                    print(f"[ModificationTransaction] Restored original snapshot successfully: {self.stash_ref}")
                else:
                    print(f"[ModificationTransaction] Warning: Failed to restore checkpoint stash: {self.stash_ref}")
            else:
                print("[ModificationTransaction] Clean workspace rollback complete. No stash restoration needed.")

        except Exception as e:
            print(f"[ModificationTransaction] Critical: Error restoring snapshot during rollback: {e}")

        self.save_to_db()
        return True

    def save_to_db(self) -> None:
        """
        Saves or updates the checkpoint transaction metadata in PostgreSQL.
        """
        import json
        session = SessionLocal()
        try:
            # Check if record exists
            exists = session.execute(
                text("SELECT 1 FROM modification_checkpoints WHERE id = :id"),
                {"id": self.checkpoint_id}
            ).fetchone()

            is_sqlite = "sqlite" in str(session.bind.url)
            files_val = json.dumps(self.modified_files) if is_sqlite else self.modified_files

            if exists:
                session.execute(
                    text("""
                        UPDATE modification_checkpoints
                        SET validation_status = :status,
                            rollback_reason = :reason,
                            modified_files = :files
                        WHERE id = :id
                    """),
                    {
                        "id": self.checkpoint_id,
                        "status": self.validation_status,
                        "reason": self.rollback_reason,
                        "files": files_val
                    }
                )
            else:
                session.execute(
                    text("""
                        INSERT INTO modification_checkpoints (id, task_id, created_at, goal, modified_files, validation_status, rollback_reason)
                        VALUES (:id, :task_id, :created_at, :goal, :files, :status, :reason)
                    """),
                    {
                        "id": self.checkpoint_id,
                        "task_id": self.task_id,
                        "created_at": self.created_at,
                        "goal": self.goal,
                        "files": files_val,
                        "status": self.validation_status,
                        "reason": self.rollback_reason
                    }
                )
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[ModificationTransaction] Warning: Failed to save checkpoint to DB: {e}")
        finally:
            session.close()

    def __enter__(self):
        self.begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback(reason=str(exc_val))
        return False  # Propagate the exception
