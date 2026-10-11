# context/assembler.py
"""
Context Assembler — strict HOT / WARM / COLD tier enforcement.

Tier rules
----------
HOT  (<2k tokens)  — always included, never firewalled
    active_file content / cursor span / diagnostics / primary symbol (top-1)

WARM (<6k tokens)  — included if budget allows
    modification_targets / retrieved_chunks (top-3) /
    callers + callees (top-3 each) / current_plan (trimmed)

COLD (max 4k, lazy) — EMPTY by default in agent mode
    reflections / repair_history / execution_history /
    failed_steps / recent_tool_outputs / architecture_notes /
    generated_code / test_failures

    Populated only when include_cold=True is passed to build() OR
    mode == "agent_deep".

Total hard cap is enforced at the end via ContextBudget.enforce_total_budget().
"""

from typing import Dict, Any, List, Optional
from memory.task_state import TaskState
from context.compression import ContextCompressor
from context.context_budget import ContextBudget, COLD_KEYS, WARM_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _head(lst: list, n: int) -> list:
    """Return at most *n* items from the front of a list."""
    if not lst:
        return []
    return lst[:n]


def _estimate(val: Any) -> int:
    return ContextBudget.estimate_tokens(val)


# ---------------------------------------------------------------------------
# AgentContextAssembler
# ---------------------------------------------------------------------------

class AgentContextAssembler:
    """
    Builds the LLM context dict using three strict tiers:
      HOT  — always in, hard cap 2k
      WARM — in if budget allows, cap 6k
      COLD — lazy, empty by default
    """

    def __init__(
        self,
        max_chunks: int = 3,         # reduced from 6 — WARM tier cap
        max_failures: int = 3,
        max_executions: int = 3,
        max_reflections: int = 2,
        max_history: int = 5,
    ):
        self.max_chunks = max_chunks
        self.max_failures = max_failures
        self.max_executions = max_executions
        self.max_reflections = max_reflections
        self.max_history = max_history
        self.compressor = ContextCompressor()

    def build(
        self,
        state: TaskState,
        mode: str = "agent",
        include_cold: bool = False,
    ) -> Dict[str, Any]:
        """Assemble context with tier-gated budget enforcement.

        Args:
            state:        Current task state.
            mode:         Execution mode string.
            include_cold: If True, populate COLD tier (default False).
        """
        mode_lower = mode.lower()
        # agent_deep explicitly requests COLD tier
        if mode_lower == "agent_deep":
            include_cold = True

        # ── HOT tier ──────────────────────────────────────────────────
        # Must stay under HOT_TOKENS. Never pruned to zero.
        active_symbols = _head(getattr(state, "active_symbols", []) or [], 1)
        diagnostics = []
        if getattr(state, "runtime_context", None):
            diagnostics = _head(
                getattr(state.runtime_context, "diagnostics", []) or [], 5
            )

        hot = {
            "goal"          : state.goal,
            "status"        : state.status,
            "current_step"  : state.current_step,
            "active_symbols": active_symbols,
            "diagnostics"   : diagnostics,
        }
        hot = ContextBudget.enforce_hot(hot)

        # ── WARM tier ─────────────────────────────────────────────────
        # Rank & trim each list. Only include if below WARM cap.
        from context.relevance_ranker import RelevanceRanker

        primary_fqn = active_symbols[-1] if active_symbols else None

        def _ranked(lst: list, limit: int) -> list:
            if not lst:
                return []
            ranked = RelevanceRanker.rank_and_budget(
                lst,
                state.goal,
                primary_fqn,
                diagnostics,
                token_limit=limit,
            )
            return ranked

        warm_chunk_budget = ContextBudget.WARM_TOKENS // 4   # ~1 500 tokens for chunks
        warm_sym_budget   = ContextBudget.WARM_TOKENS // 8   # ~750 per symbol list

        raw_chunks = getattr(state, "retrieved_chunks", []) or []
        primary_files = list(getattr(state, "modification_targets", []) or [])
        ranked_chunks = _ranked(_head(raw_chunks, self.max_chunks * 2), warm_chunk_budget)
        compressed_chunks = self.compressor.compress_chunks(
            ranked_chunks, primary_files=primary_files
        )

        warm = {
            "modification_targets": _ranked(
                getattr(state, "modification_targets", []) or [], warm_sym_budget
            ),
            "modified_files"      : _ranked(
                getattr(state, "modified_files", []) or [], warm_sym_budget
            ),
            "retrieved_chunks"    : compressed_chunks,
            "callers"             : _head(
                _ranked(getattr(state, "callers", []) or [], warm_sym_budget), 3
            ),
            "callees"             : _head(
                _ranked(getattr(state, "callees", []) or [], warm_sym_budget), 3
            ),
            "current_plan"        : _ranked(
                getattr(state, "current_plan", []) or [], warm_sym_budget
            ),
            "pending_executions"  : _ranked(
                getattr(state, "pending_executions", []) or [], warm_sym_budget
            ),
            "touched_files"       : _ranked(
                getattr(state, "touched_files", []) or [], warm_sym_budget
            ),
        }
        warm = ContextBudget.enforce_warm(warm)

        # ── COLD tier ─────────────────────────────────────────────────
        # Empty by default. Populated only when include_cold=True.
        cold: Dict[str, Any] = {
            "reflections"        : [],
            "repair_history"     : [],
            "execution_history"  : [],
            "failed_steps"       : [],
            "recent_tool_outputs": [],
            "architecture_notes" : [],
            "generated_code"     : [],
            "test_failures"      : [],
        }

        if include_cold:
            cold_budget = ContextBudget.COLD_TOKENS // len(cold)
            cold = {
                "reflections"        : _ranked(
                    getattr(state, "reflections", []) or [], cold_budget
                ),
                "repair_history"     : _ranked(
                    getattr(state, "repair_history", []) or [], cold_budget
                ),
                "execution_history"  : _head(
                    getattr(state, "execution_history", []) or [],
                    self.max_executions
                ),
                "failed_steps"       : _head(
                    getattr(state, "failed_steps", []) or [], self.max_failures
                ),
                "recent_tool_outputs": _ranked(
                    getattr(state, "tool_outputs", []) or [], cold_budget
                ),
                "architecture_notes" : _ranked(
                    getattr(state, "architecture_notes", []) or [], cold_budget
                ),
                "generated_code"     : _ranked(
                    getattr(state, "generated_code", []) or [], cold_budget
                ),
                "test_failures"      : _head(
                    getattr(state, "test_failures", []) or [], self.max_failures
                ),
            }
            cold = ContextBudget.enforce_cold(cold)

        # ── Non-edit / non-agent modes: strip COLD entirely ───────────
        if mode_lower in ("inline", "inline_edit", "patch", "patch_edit",
                          "assist", "code_assist"):
            cold = {k: [] for k in cold}

        # ── Assemble & enforce total budget ───────────────────────────
        ctx: Dict[str, Any] = {
            **hot,
            **warm,
            **cold,
            "runtime_memory": {
                "iterations"    : state.runtime_memory.total_iterations
                                  if getattr(state, "runtime_memory", None) else 0,
                "tool_calls"    : state.runtime_memory.tool_call_count
                                  if getattr(state, "runtime_memory", None) else 0,
                "retrievals"    : state.runtime_memory.retrieval_count
                                  if getattr(state, "runtime_memory", None) else 0,
                "repairs"       : state.runtime_memory.repair_count
                                  if getattr(state, "runtime_memory", None) else 0,
                "runtime_errors": state.runtime_memory.runtime_errors
                                  if getattr(state, "runtime_memory", None) else [],
            },
            "loop_warning": self.detect_loops(state),
        }

        ctx = ContextBudget.enforce_total_budget(ctx, mode=mode_lower)
        return ctx

    def detect_loops(self, state: TaskState) -> bool:
        recent = state.completed_steps[-6:] if getattr(state, "completed_steps", None) else []
        if len(recent) < 6:
            return False
        return len(set(recent)) <= 2


# ---------------------------------------------------------------------------
# ContextAssembler (public façade — backward compatible)
# ---------------------------------------------------------------------------

class ContextAssembler:
    def __init__(
        self,
        max_chunks: int = 3,
        max_failures: int = 3,
        max_executions: int = 3,
        max_reflections: int = 2,
        max_history: int = 5,
    ):
        self.agent_assembler = AgentContextAssembler(
            max_chunks=max_chunks,
            max_failures=max_failures,
            max_executions=max_executions,
            max_reflections=max_reflections,
            max_history=max_history,
        )

    def build(
        self,
        state: TaskState,
        mode: Optional[str] = None,
        include_cold: bool = False,
    ) -> Dict[str, Any]:
        # Determine mode
        if not mode:
            active_goal = getattr(state, "goal", "")
            if active_goal:
                try:
                    from runtime.fast_path_router import FastPathRouter
                    route_decision = FastPathRouter.route(active_goal)
                    mode = str(route_decision.execution_mode)
                except Exception:
                    pass
        if not mode:
            mode = "agent"

        mode_lower = mode.lower()

        # patch / inline — use PatchContextBuilder (lightweight path)
        if mode_lower in ("patch", "inline", "inline_edit", "patch_edit"):
            try:
                from context.patch_context import PatchContextBuilder, patch_context_to_prompt_context
                from runtime.editor.models import EditorState

                editor_state = getattr(state, "editor_state", None)
                if not editor_state and getattr(state, "runtime_memory", None):
                    editor_state = getattr(state.runtime_memory, "editor_state", None)
                if not editor_state:
                    active_file = (
                        getattr(state, "active_file", "")
                        or (state.modification_targets[0]
                            if getattr(state, "modification_targets", None) else "")
                    )
                    editor_state = EditorState(
                        active_file=active_file,
                        cursor_line=1,
                        unsaved_buffer=getattr(state, "unsaved_buffer", ""),
                    )
                try:
                    from retrieval.service import RetrievalFacade
                    pipeline = RetrievalFacade().pipeline
                except Exception:
                    pipeline = None

                builder = PatchContextBuilder(pipeline)
                patch_ctx = builder.build(editor_state, state.goal)
                return patch_context_to_prompt_context(patch_ctx)
            except Exception:
                pass  # fall through to agent assembler

        return self.agent_assembler.build(state, mode=mode, include_cold=include_cold)
