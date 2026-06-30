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

            # Prune matching tool outputs
            pruned_outputs = []
            if len(state.tool_outputs) > 20:
                prune_out_count = len(state.tool_outputs) - 20
                pruned_outputs = state.tool_outputs[:prune_out_count]
                state.tool_outputs = state.tool_outputs[prune_out_count:]

            # Prune execution history
            if len(state.execution_history) > 30:
                prune_hist_count = len(state.execution_history) - 20
                state.execution_history = state.execution_history[prune_hist_count:]

            # Prune command history
            if len(state.command_history) > 30:
                prune_cmd_count = len(state.command_history) - 20
                state.command_history = state.command_history[prune_cmd_count:]

            # Build LLM-driven episodic summary
            summary_text = self._build_episodic_summary(pruned_steps, pruned_outputs)

            # Persist Layer 2 summary to Postgres/SQLite
            task_id = state.session_id or getattr(state, "task_id", "default_task")
            self._save_to_db(task_id, summary_text, start_step, end_step)

            # Store summary in task state metadata
            if not isinstance(state.metadata, dict):
                state.metadata = {}
            if "episodic_summaries" not in state.metadata:
                state.metadata["episodic_summaries"] = []
            state.metadata["episodic_summaries"].append({
                "summary": summary_text,
                "start_step": start_step,
                "end_step": end_step,
                "timestamp": datetime.utcnow().isoformat()
            })

            # Set compacted steps in hot memory state
            state.completed_steps = remaining_steps

    def _build_episodic_summary(self, steps: list[str], outputs: list[dict]) -> str:
        """
        Queries local LLM to build a concise, human-readable episodic summary of pruned steps.
        """
        # Collect outputs description for context
        outputs_desc = []
        for out in outputs:
            out_name = out.get("name") or out.get("tool") or "tool"
            out_val = str(out.get("output") or out.get("result") or "")[:200]
            outputs_desc.append(f"Tool {out_name} returned: {out_val}")

        from llm.ollama_client import OllamaClient
        from inference.router import TaskType

        prompt = f"""You are a precise software engineering agent summarizer.
Summarize the following series of completed agent steps and tool outputs into a single-sentence episodic summary.
Focus on: what was attempted, what files/symbols were targeted, and what failures or successes occurred.

COMPLETED STEPS:
{", ".join(steps)}

TOOL OUTPUTS:
{" | ".join(outputs_desc)}

Write a single-sentence summary (e.g., "attempted patch to EmployeeService, tests failed due to compilation errors"). Do not include any intro or other commentary.
"""
        try:
            client = OllamaClient()
            summary_text = client.chat([{"role": "user", "content": prompt}], task_type=TaskType.CHAT)
            return summary_text.strip()
        except Exception as e:
            print(f"[MemoryCompactor] LLM summary generation failed: {e}. Falling back to default list.")
            step_counts = {}
            for step in steps:
                step_counts[step] = step_counts.get(step, 0) + 1
            summary_parts = []
            for step_name, count in step_counts.items():
                if count > 1:
                    summary_parts.append(f"{step_name} ({count} times)")
                else:
                    summary_parts.append(step_name)
            return "Compacted steps: " + ", ".join(summary_parts)

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
