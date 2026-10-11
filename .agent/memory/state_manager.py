# memory/state_manager.py

from typing import (
    Optional,
    List
)
from pathlib import Path

from memory.task_state import (
    TaskState
)

from memory.persistence import (
    StatePersistence
)

from memory.execution_history import (
    ExecutionRecord
)


from memory.event_store import EventStore
from memory.artifact_store import ArtifactStore


class StateManager:

    def __init__(self):

        self.state: Optional[
            TaskState
        ] = None

        self.task_id = None
        self.ephemeral = True

        self.persistence = (
            StatePersistence()
        )
        self.event_store = EventStore()
        self.artifact_store = ArtifactStore()

    # =====================================================
    # SNAPSHOT ISOLATION
    # =====================================================

    def validate_snapshot(self, repo_root: str = ".") -> Optional["SnapshotValidationResult"]:
        """
        Compare the stored snapshot_id in the current TaskState against the
        live repository state. Returns a SnapshotValidationResult.

        Call this after load_state() to detect if the repo changed while the
        task was suspended. If stale, call apply_snapshot_invalidation() to
        clear derived intelligence before resuming execution.

        Returns None if no state is loaded or snapshot_id was never recorded
        (legacy tasks without snapshot support).
        """
        self._ensure_state()

        stored_id = getattr(self.state, "snapshot_id", "") or ""
        if not stored_id:
            return None

        try:
            from repository.snapshot_manager import SnapshotManager
            result = SnapshotManager().build_validation_result(
                stored_snapshot_id=stored_id,
                repo_root=repo_root,
            )
            return result
        except Exception as e:
            print(f"[StateManager] Snapshot validation failed (non-fatal): {e}")
            return None

    def apply_snapshot_invalidation(self, result, repo_root: str = "."):
        """
        Apply selective invalidation based on a SnapshotValidationResult.

        Clears all ephemeral/derived fields (retrieved_chunks, active_symbols,
        tool_outputs, etc.) while preserving control-plane state (goal,
        current_plan, modification_targets).

        Also updates state.snapshot_id to the current snapshot so subsequent
        resume checks start fresh.
        """
        if result is None or result.is_fresh:
            return

        self._ensure_state()

        cleared = []
        for field_name in result.stale_fields:
            if hasattr(self.state, field_name):
                default = [] if field_name not in ("git_diff", "last_confidence") else ("" if field_name == "git_diff" else 0.0)
                setattr(self.state, field_name, default)
                cleared.append(field_name)

        # Update snapshot_id to current so next resume is fresh
        self.state.snapshot_id = result.current_snapshot.snapshot_id
        self.state.dirty_files_at_creation = result.current_snapshot.dirty_files

        if cleared:
            print(
                f"[StateManager] Snapshot stale — cleared {len(cleared)} fields "
                f"(changed_files={result.changed_files})"
            )

        self._touch()


    # =====================================================
    # TASK
    # =====================================================

    def create_task(
        self,
        goal: str,
        task_id: str
    ) -> TaskState:

        self.task_id = task_id

        self.state = TaskState(
            goal=goal
        )

        self.save_state()

        return self.state

    def load_state(
        self,
        task_id: str
    ) -> TaskState:

        self.state = (
            self.persistence.load(
                task_id
            )
        )

        self.task_id = task_id

        return self.state

    def save_state(self):

        self._ensure_state()

        if getattr(self, "ephemeral", False):
            return

        self.persistence.save(
            self.state,
            self.task_id
        )

    def get_state(self) -> TaskState:

        self._ensure_state()

        return self.state

    def task_exists(
        self,
        task_id: str
    ) -> bool:

        return self.persistence.exists(
            task_id
        )

    # =====================================================
    # PLAN
    # =====================================================

    def set_execution_plan(self, plan):
        self._ensure_state()
        self.state.execution_plan = plan.to_dict() if plan else None
        self._touch()

    def get_execution_plan(self):
        self._ensure_state()
        if not self.state.execution_plan:
            return None
        from planning.execution_plan import ExecutionPlan
        return ExecutionPlan.from_dict(self.state.execution_plan)

    def set_execution_state(self, state_val: str):
        self._ensure_state()
        self.state.execution_state = state_val
        self._touch()

    def get_execution_state(self) -> str:
        self._ensure_state()
        return self.state.execution_state or "PLANNING"

    def set_plan(
        self,
        actions
    ):

        self._ensure_state()

        self.state.current_plan = [

            action.to_dict()

            if hasattr(
                action,
                "to_dict"
            )
            else action

            for action in actions
        ]

        self._touch()

    # =====================================================
    # EXECUTION QUEUE
    # =====================================================

    def push_execution(
        self,
        execution
    ):

        self._ensure_state()

        execution_dict = (

            execution.to_dict()

            if hasattr(
                execution,
                "to_dict"
            )
            else execution
        )

        existing = {

            item["action_id"]

            for item in
            self.state.pending_executions
        }

        if (
            execution_dict["action_id"]
            in existing
        ):
            return

        self.state.pending_executions.append(
            execution_dict
        )

        self.sort_execution_queue()

        self._touch()

    def push_executions(
        self,
        executions
    ):

        for execution in executions:

            self.push_execution(
                execution
            )

    def pop_next_execution(self):

        self._ensure_state()

        if not self.state.pending_executions:

            return None

        execution = (
            self.state.pending_executions.pop(
                0
            )
        )

        self._touch()

        return execution

    def retry_execution(
        self,
        execution
    ):

        self._ensure_state()

        execution["retries"] = (
            execution.get(
                "retries",
                0
            ) + 1
        )

        execution["status"] = (
            "pending"
        )

        self.state.pending_executions.append(
            execution
        )

        self.sort_execution_queue()

        self._touch()

    def get_pending_executions(self):

        self._ensure_state()

        return (
            self.state.pending_executions
        )

    def sort_execution_queue(self):

        self.state.pending_executions.sort(

            key=lambda x: (

                x.get(
                    "priority",
                    999
                ),

                x.get(
                    "retries",
                    0
                )
            )
        )

    # =====================================================
    # TOOL OUTPUTS
    # =====================================================

    def add_tool_output(
        self,
        tool_name,
        output
    ):

        self._ensure_state()

        status = "success"

        if isinstance(
            output,
            dict
        ):

            if (
                output.get("error")
                or output.get(
                    "success"
                ) is False
            ):
                status = "failed"

        self.state.tool_outputs.append({

            "tool":
                tool_name,

            "status":
                status,

            "result":
                output
        })

        self._touch()

    # =====================================================
    # REFLECTIONS
    # =====================================================

    def add_reflection(
        self,
        reflection: str
    ):

        self._ensure_state()

        self.state.reflections.append(
            reflection
        )

        self._touch()

    # =====================================================
    # EXECUTION HISTORY
    # =====================================================

    def add_execution_record(
        self,
        record: ExecutionRecord
    ):

        self._ensure_state()

        event_data = {
            "action_id":
                record.action_id,

            "tool":
                record.tool,

            "status":
                record.status,

            "started_at":
                record.started_at,

            "completed_at":
                record.completed_at,

            "duration_seconds":
                record.duration_seconds,

            "retries":
                record.retries,

            "success":
                record.success,

            "input_data":
                record.input_data,

            "output_data":
                record.output_data,

            "error":
                record.error
        }

        self.state.execution_history.append(event_data)

        try:
            if not getattr(self, "ephemeral", False):
                self.event_store.append_event(self.task_id, event_data)
        except Exception as e:
            print(f"[StateManager] Failed to journal execution event: {e}")

        self._touch()

    # =====================================================
    # RETRIEVAL
    # =====================================================

    def add_chunk(
        self,
        chunk
    ):

        self._ensure_state()

        chunk_id = chunk.get(
            "chunk_id"
        )

        existing = {

            c.get(
                "chunk_id"
            )

            for c in
            self.state.retrieved_chunks
        }

        if (
            chunk_id
            and
            chunk_id in existing
        ):
            return

        self.state.retrieved_chunks.append(
            chunk
        )

        #
        # Automatically register
        # retrieved file as a
        # modification candidate.
        #

        path = chunk.get(
            "file"
        )

        if path:

            self.add_modification_target(
                path
            )

        self._touch()

    # =====================================================
    # MODIFICATION TARGETS
    # =====================================================

    def add_modification_target(
        self,
        file_path: str
    ):

        self._ensure_state()

        if not file_path:
            return

        file_path = file_path.strip()

        if not file_path:
            return

        # Normalize paths to prevent duplicate target entry variants
        file_path = str(Path(file_path))

        if (
            file_path
            not in self.state.modification_targets
        ):

            self.state.modification_targets.append(
                file_path
            )

            self._touch()

    def set_modification_targets(
        self,
        files: List[str]
    ):

        self._ensure_state()

        unique = []

        for file_path in files:

            if not file_path:
                continue

            file_path = file_path.strip()

            if not file_path:
                continue

            # Normalize structural paths prior to safety checking
            file_path = str(Path(file_path))

            if (
                file_path
                not in unique
            ):
                unique.append(
                    file_path
                )

        self.state.modification_targets = (
            unique
        )

        self._touch()

    # =====================================================
    # RUNTIME METRICS
    # =====================================================

    def increment_tool_calls(self):

        self._ensure_state()

        self.state.runtime_memory.tool_call_count += 1

        self._touch()

    def increment_repairs(
        self,
        success=False
    ):

        self._ensure_state()

        self.state.runtime_memory.repair_count += 1

        if success:

            self.state.runtime_memory.successful_repairs += 1

        else:

            self.state.runtime_memory.failed_repairs += 1

        self._touch()

    def increment_retrievals(self):

        self._ensure_state()

        self.state.runtime_memory.retrieval_count += 1

        self._touch()

    # =====================================================
    # INTERNALS
    # =====================================================

    def _ensure_state(self):

        if self.state is None:

            raise RuntimeError(
                "TaskState not initialized."
            )

    def _touch(self):

        self.state.touch()

        if self.task_id:

            self.save_state()

    # =====================================================
    # PIPELINE CACHING
    # =====================================================

    def set_last_modification(
        self,
        modification
    ):

        self._ensure_state()

        self.state.metadata[
            "last_modification"
        ] = modification

        self._touch()

    def get_last_modification(self):

        self._ensure_state()

        return self.state.metadata.get(
            "last_modification"
        )

    def set_last_patch(
        self,
        patch
    ):

        self._ensure_state()

        self.state.metadata[
            "last_patch"
        ] = patch

        self._touch()

    def get_last_patch(self):

        self._ensure_state()

        return self.state.metadata.get(
            "last_patch"
        )
