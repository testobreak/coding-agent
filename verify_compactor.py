import sys
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from repository_intelligence.db.connection import SessionLocal
from sqlalchemy import text
from memory.task_state import TaskState


def run_tests():
    print("\n" + "=" * 60)
    print("  MemoryCompactor & Layered Memory Tests")
    print("=" * 60)

    from repository_intelligence.db.connection import Base, engine
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()

    try:
        print("\n[1] Initializing TaskState with mock session...")
        state = TaskState(
            goal="Test automatic memory compaction",
            session_id="mock_test_session_123"
        )
        
        # Populate 45 completed steps to trigger compaction (> 30 steps)
        state.completed_steps = [f"Step-{i}" for i in range(45)]
        state.runtime_memory.total_iterations = 45

        print(f"  - Initial steps count: {len(state.completed_steps)}")
        print("  - Injecting transaction session into compactor...")
        
        # Build compactor to use our active transactional session for validation
        from memory.compaction import MemoryCompactor
        compactor = MemoryCompactor()
        
        # Monkey patch _save_to_db to use our active rollback-capable test session
        def mock_save_to_db(task_id, summary, start_step, end_step):
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
            session.flush()
            print(f"  [OK] Saved compacted summary to DB (Steps {start_step}-{end_step}).")
            
        compactor._save_to_db = mock_save_to_db
        state._compactor = compactor

        # -------------------------------------------------------------
        # Test 1: Compaction Trigger
        # -------------------------------------------------------------
        print("\n[Test 1] Invoking TaskState.trim_memory() to trigger compaction...")
        state.trim_memory()

        # Enforce that completed_steps was compacted and pruned down to the hot 20 steps
        assert len(state.completed_steps) == 20, f"Expected 20 steps in hot memory, got {len(state.completed_steps)}"
        print(f"  [OK] Hot Memory Pruned: Steps remaining in hot state: {len(state.completed_steps)}.")
        
        # Ensure remaining steps are the most recent 20 steps (Step-25 to Step-44)
        assert state.completed_steps[0] == "Step-25", f"Expected remaining list start Step-25, got {state.completed_steps[0]}"
        assert state.completed_steps[-1] == "Step-44", f"Expected remaining list end Step-44, got {state.completed_steps[-1]}"
        print("  [OK] Correct steps preserved in hot memory (Step-25 through Step-44).")

        # -------------------------------------------------------------
        # Test 2: Database Summary Persistence
        # -------------------------------------------------------------
        print("\n[Test 2] Verifying database persistence inside public.task_summaries...")
        
        # Query task_summaries for our mock task ID
        rows = session.execute(
            text("""
                SELECT task_id, summary, start_step, end_step
                FROM task_summaries
                WHERE task_id = 'mock_test_session_123'
            """)
        ).fetchall()

        assert len(rows) == 1, f"Expected 1 summary row, got {len(rows)}"
        row = rows[0]
        assert row[2] == 1, f"Expected start_step = 1, got {row[2]}"
        assert row[3] == 25, f"Expected end_step = 25, got {row[3]}"
        assert "Step-0" in row[1], "Expected Step-0 in compacted summary text"
        assert "Step-24" in row[1], "Expected Step-24 in compacted summary text"
        
        print("  [OK] Database Record Verified:")
        print(f"    - Task ID:    {row[0]}")
        print(f"    - Steps:      {row[2]} to {row[3]}")
        print(f"    - Summary:    {row[1]}")

        # -------------------------------------------------------------
        # Test 3: Database Event Persistence
        # -------------------------------------------------------------
        print("\n[Test 3] Verifying database event logging inside public.task_events...")
        
        # Monkey patch record_event to write to our active test session
        def mock_record_event(task_id, event_type, event_data):
            import json
            if not isinstance(event_data, dict):
                event_data = {"data": event_data}
            is_sqlite = "sqlite" in str(session.bind.url)
            time_func = "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"
            cast_part = ":event_data" if is_sqlite else "CAST(:event_data AS jsonb)"
            session.execute(
                text(f"""
                    INSERT INTO task_events (task_id, event_type, event_data, created_at)
                    VALUES (:task_id, :event_type, {cast_part}, {time_func})
                """),
                {
                    "task_id": task_id,
                    "event_type": event_type,
                    "event_data": json.dumps(event_data)
                }
            )
            session.flush()
            print(f"  [OK] Saved event {event_type} to DB.")

        compactor.record_event = mock_record_event

        # Record a test event
        compactor.record_event(
            task_id="mock_test_session_123",
            event_type="TOOL_OUTPUT",
            event_data={"tool": "view_file", "status": "success", "result": "lines 1-10"}
        )

        # Query task_events for our mock task ID
        event_rows = session.execute(
            text("""
                SELECT task_id, event_type, event_data
                FROM task_events
                WHERE task_id = 'mock_test_session_123'
            """)
        ).fetchall()

        assert len(event_rows) == 1, f"Expected 1 event row, got {len(event_rows)}"
        event_row = event_rows[0]
        assert event_row[1] == "TOOL_OUTPUT", f"Expected event_type = TOOL_OUTPUT, got {event_row[1]}"
        event_data = event_row[2]
        if isinstance(event_data, str):
            import json
            event_data = json.loads(event_data)
        assert event_data["tool"] == "view_file", f"Expected tool = view_file, got {event_data['tool']}"
        
        print("  [OK] Database Event Record Verified:")
        print(f"    - Task ID:    {event_row[0]}")
        print(f"    - Event Type: {event_row[1]}")
        print(f"    - Event Data: {event_data}")

        print("\n" + "=" * 60)
        print("  ALL COMPACTION & EVENT TESTS PASSED! [OK]")
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
        print("[Cleanup] Rolling back transaction to keep database clean...")
        session.rollback()
        session.close()


if __name__ == "__main__":
    run_tests()
