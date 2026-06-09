from datetime import datetime
from repository_intelligence.db.connection import SessionLocal
from sqlalchemy import text
import json


class MemoryCompactor:
    """
    Enterprise memory compactor that prunes completed steps and persists 
    compacted summaries in the PostgreSQL `task_summaries` table.
    """

    def __init__(self):
        self.compact_run_count = 0
        self.ensure_tables()

    def ensure_tables(self) -> None:
        """
        Ensures both task_summaries and task_events tables exist in the database.
        """
        session = SessionLocal()
        try:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS task_summaries (
                    id SERIAL PRIMARY KEY,
                    task_id TEXT,
                    summary TEXT,
                    start_step INTEGER,
                    end_step INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS task_events (
                    id SERIAL PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_task_events_type ON task_events(event_type);
            """))
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[MemoryCompactor] Warning: Failed to ensure memory tables: {e}")
        finally:
            session.close()

    def record_event(self, task_id: str, event_type: str, event_data: dict, session=None) -> None:
        """
        Records a memory/execution event in public.task_events.
        """
        if not isinstance(event_data, dict):
            event_data = {"data": event_data}

        # Resolve DB session to inspect binding URL
        test_session = session or SessionLocal()
        try:
            is_sqlite = "sqlite" in str(test_session.bind.url)
        except Exception:
            is_sqlite = False
        finally:
            if not session:
                test_session.close()

        if is_sqlite:
            sql = """
                INSERT INTO task_events (task_id, event_type, event_data, created_at)
                VALUES (:task_id, :event_type, :event_data, CURRENT_TIMESTAMP)
            """
        else:
            sql = """
                INSERT INTO task_events (task_id, event_type, event_data, created_at)
                VALUES (:task_id, :event_type, CAST(:event_data AS jsonb), NOW())
            """
        params = {
            "task_id": task_id,
            "event_type": event_type,
            "event_data": json.dumps(event_data)
        }

        if session:
            session.execute(text(sql), params)
            session.flush()
        else:
            local_session = SessionLocal()
            try:
                local_session.execute(text(sql), params)
                local_session.commit()
            except Exception as e:
                local_session.rollback()
                print(f"[MemoryCompactor] Warning: Failed to record event {event_type}: {e}")
            finally:
                local_session.close()

    def compact(self, state) -> None:
        """
        Executes automatic state pruning and writes summarized checkpoints
        to the task_summaries database table.
        """
        self.compact_run_count += 1
        
        # We compact if we have more than 30 completed steps (keeping the hot last 20)
        if len(state.completed_steps) > 30:
            prune_count = len(state.completed_steps) - 20
            pruned_steps = state.completed_steps[:prune_count]
            remaining_steps = state.completed_steps[prune_count:]

            # Enforce step index tracking
            start_step = state.runtime_memory.total_iterations - len(state.completed_steps) + 1
            end_step = start_step + prune_count - 1

            summary_text = self._build_summary(pruned_steps)

            # Persist Layer 2 summary to Postgres
            task_id = state.session_id or getattr(state, "task_id", "default_task")
            self._save_to_db(task_id, summary_text, start_step, end_step)

            # Set compacted steps in hot memory state
            state.completed_steps = remaining_steps

    def _build_summary(self, steps: list[str]) -> str:
        """
        Builds a clean, human-readable summary of pruned completed steps.
        """
        step_counts = {}
        for step in steps:
            step_counts[step] = step_counts.get(step, 0) + 1

        summary_parts = []
        for step_name, count in step_counts.items():
            if count > 1:
                summary_parts.append(f"{step_name} ({count} times)")
            else:
                summary_parts.append(step_name)

        return "Compacted completed steps: " + ", ".join(summary_parts)

    def _save_to_db(self, task_id: str, summary: str, start_step: int, end_step: int) -> None:
        """
        Persists a compacted summary record inside PostgreSQL public.task_summaries.
        """
        session = SessionLocal()
        try:
            is_sqlite = "sqlite" in str(session.bind.url)
            time_func = "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"
            session.execute(
                text(f"""
                    INSERT INTO task_summaries (task_id, summary, start_step, end_step, created_at)
                    VALUES (:task_id, :summary, :start_step, :end_step, {time_func})
                """),
                {
                    "task_id": task_id,
                    "summary": summary,
                    "start_step": start_step,
                    "end_step": end_step
                }
            )
            session.commit()
            print(f"[MemoryCompactor] Compacted steps {start_step}-{end_step} saved to DB.")
        except Exception as e:
            session.rollback()
            print(f"[MemoryCompactor] Warning: Failed to save task summary: {e}")
        finally:
            session.close()
