# context/assembler.py

from typing import Dict, Any, List

from memory.task_state import (
    TaskState
)

from context.compression import (
    ContextCompressor
)


class ContextAssembler:

    def __init__(
        self,
        max_chunks: int = 6,
        max_failures: int = 5,
        max_executions: int = 5,
        max_reflections: int = 3,
        max_history: int = 10
    ):

        self.max_chunks = max_chunks

        self.max_failures = max_failures

        self.max_executions = max_executions

        self.max_reflections = (
            max_reflections
        )

        self.max_history = max_history

        self.compressor = (
            ContextCompressor()
        )

    # =====================================================
    # MAIN
    # =====================================================

    def build(
        self,
        state: TaskState
    ) -> Dict[str, Any]:

        # Resolve target files to identify primary files for full code inclusion
        primary_files = []
        if getattr(state, "modification_targets", None):
            primary_files = list(state.modification_targets)
        else:
            # Fallback to the first few files in retrieved chunks
            seen_files = []
            for chunk in (state.retrieved_chunks or []):
                f = chunk.get("file")
                if f and f not in seen_files:
                    seen_files.append(f)
            primary_files = seen_files[:2]

        retrieved_chunks = (
            self.compressor.compress_chunks(
                state.retrieved_chunks[-self.max_chunks:],
                primary_files=primary_files
            )
        )

        recent_outputs = (
            self.compressor
            .compress_tool_outputs(

                state.tool_outputs[-5:]
            )
        )

        return {

            # =============================================
            # CORE
            # =============================================

            "goal":
                state.goal,

            "status":
                state.status,

            "current_step":
                state.current_step,

            # =============================================
            # ACTIVE EXECUTION
            # =============================================

            "pending_executions":

                state.pending_executions[
                    :self.max_executions
                ],

            "current_plan":

                state.current_plan[-10:],

            # =============================================
            # FAILURES
            # =============================================

            "failed_steps":

                state.failed_steps[
                    -self.max_failures:
                ],

            "test_failures":

                state.test_failures[
                    -self.max_failures:
                ],

            "repair_history":

                state.repair_history[-5:],

            # =============================================
            # RETRIEVAL
            # =============================================

            "retrieved_chunks":
                retrieved_chunks,

            "active_symbols":

                state.active_symbols[-20:],

            "touched_files":

                state.touched_files[-20:],

            # =============================================
            # MODIFICATION HISTORY
            # =============================================

            "modification_targets":
                getattr(state, "modification_targets", [])[-20:],

            "modified_files":
                getattr(state, "modified_files", [])[-20:],

            "generated_code":
                getattr(state, "generated_code", [])[-10:],

            # =============================================
            # MEMORY
            # =============================================

            "reflections":

                state.reflections[
                    -self.max_reflections:
                ],

            "architecture_notes":

                state.architecture_notes[
                    -10:
                ],

            # =============================================
            # EXECUTION HISTORY
            # =============================================

            "recent_tool_outputs":
                recent_outputs,

            "execution_history":

                state.execution_history[
                    -self.max_history:
                ],

            # =============================================
            # RUNTIME METRICS
            # =============================================

            "runtime_memory": {

                "iterations":
                    state.runtime_memory
                    .total_iterations,

                "tool_calls":
                    state.runtime_memory
                    .tool_call_count,

                "retrievals":
                    state.runtime_memory
                    .retrieval_count,

                "repairs":
                    state.runtime_memory
                    .repair_count,

                "runtime_errors":
                    state.runtime_memory
                    .runtime_errors
            },

            # =============================================
            # LOOP DETECTION
            # =============================================

            "loop_warning":
                self.detect_loops(state)
        }

    # =====================================================
    # LOOP DETECTION
    # =====================================================

    def detect_loops(
        self,
        state: TaskState
    ):

        recent = state.completed_steps[-6:]

        if len(recent) < 6:
            return False

        unique = len(set(recent))

        return unique <= 2
