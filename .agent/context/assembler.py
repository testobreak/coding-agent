# context/assembler.py

from typing import Dict, Any, List, Optional
from memory.task_state import TaskState
from context.compression import ContextCompressor

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
        self.max_reflections = max_reflections
        self.max_history = max_history
        self.compressor = ContextCompressor()

    def build(
        self,
        state: TaskState,
        mode: Optional[str] = None
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

        from context.policy_engine import ContextPolicyEngine
        budget = ContextPolicyEngine.get_budget(mode)
        firewalled = ContextPolicyEngine.is_firewalled(mode)
        
        # Resolve primary symbol FQN to assist ranking
        primary_symbol_fqn = None
        if getattr(state, "active_symbols", None):
            primary_symbol_fqn = state.active_symbols[-1]

        # Diagnostics for scoring
        diagnostics = []
        if getattr(state, "runtime_context", None) and getattr(state.runtime_context, "diagnostics", None):
            diagnostics = state.runtime_context.diagnostics

        from context.relevance_ranker import RelevanceRanker

        # 1. Tier 1 (Mandatory) Budgets
        tier1_limit = budget.get("tier1", 1800)
        pending_executions = RelevanceRanker.rank_and_budget(
            getattr(state, "pending_executions", []) or [],
            state.goal, primary_symbol_fqn, diagnostics,
            token_limit=tier1_limit // 4
        )
        current_plan = RelevanceRanker.rank_and_budget(
            getattr(state, "current_plan", []) or [],
            state.goal, primary_symbol_fqn, diagnostics,
            token_limit=tier1_limit // 4
        )

        # 2. Tier 2 (Structural) Budgets
        tier2_limit = budget.get("tier2", 2500)
        active_symbols = RelevanceRanker.rank_and_budget(
            getattr(state, "active_symbols", []) or [],
            state.goal, primary_symbol_fqn, diagnostics,
            token_limit=tier2_limit // 6
        )
        touched_files = RelevanceRanker.rank_and_budget(
            getattr(state, "touched_files", []) or [],
            state.goal, primary_symbol_fqn, diagnostics,
            token_limit=tier2_limit // 6
        )
        modification_targets = RelevanceRanker.rank_and_budget(
            getattr(state, "modification_targets", []) or [],
            state.goal, primary_symbol_fqn, diagnostics,
            token_limit=tier2_limit // 6
        )
        modified_files = RelevanceRanker.rank_and_budget(
            getattr(state, "modified_files", []) or [],
            state.goal, primary_symbol_fqn, diagnostics,
            token_limit=tier2_limit // 6
        )
        callers = RelevanceRanker.rank_and_budget(
            getattr(state, "callers", []) or [],
            state.goal, primary_symbol_fqn, diagnostics,
            token_limit=tier2_limit // 6
        )
        callees = RelevanceRanker.rank_and_budget(
            getattr(state, "callees", []) or [],
            state.goal, primary_symbol_fqn, diagnostics,
            token_limit=tier2_limit // 6
        )

        # 3. Tier 3 (Retrieval memory) Budgets
        tier3_limit = budget.get("tier3", 1500)
        if firewalled:
            # Firewall active: disable memory elements completely!
            retrieved_chunks = []
            recent_outputs = []
            execution_history = []
            reflections = []
            architecture_notes = []
            failed_steps = []
            test_failures = []
            repair_history = []
            generated_code = []
        else:
            limit_each = tier3_limit // 9
            
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

            raw_chunks = getattr(state, "retrieved_chunks", []) or []
            ranked_chunks = RelevanceRanker.rank_and_budget(
                raw_chunks,
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )
            retrieved_chunks = self.compressor.compress_chunks(
                ranked_chunks,
                primary_files=primary_files
            )

            raw_outputs = getattr(state, "tool_outputs", []) or []
            ranked_outputs = RelevanceRanker.rank_and_budget(
                raw_outputs,
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )
            recent_outputs = self.compressor.compress_tool_outputs(ranked_outputs)

            execution_history = RelevanceRanker.rank_and_budget(
                getattr(state, "execution_history", []) or [],
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )
            reflections = RelevanceRanker.rank_and_budget(
                getattr(state, "reflections", []) or [],
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )
            architecture_notes = RelevanceRanker.rank_and_budget(
                getattr(state, "architecture_notes", []) or [],
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )
            failed_steps = RelevanceRanker.rank_and_budget(
                getattr(state, "failed_steps", []) or [],
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )
            test_failures = RelevanceRanker.rank_and_budget(
                getattr(state, "test_failures", []) or [],
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )
            repair_history = RelevanceRanker.rank_and_budget(
                getattr(state, "repair_history", []) or [],
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )
            generated_code = RelevanceRanker.rank_and_budget(
                getattr(state, "generated_code", []) or [],
                state.goal, primary_symbol_fqn, diagnostics,
                token_limit=limit_each
            )

        return {
            "goal": state.goal,
            "status": state.status,
            "current_step": state.current_step,
            "pending_executions": pending_executions,
            "current_plan": current_plan,
            "failed_steps": failed_steps,
            "test_failures": test_failures,
            "repair_history": repair_history,
            "retrieved_chunks": retrieved_chunks,
            "active_symbols": active_symbols,
            "touched_files": touched_files,
            "modification_targets": modification_targets,
            "modified_files": modified_files,
            "generated_code": generated_code,
            "reflections": reflections,
            "architecture_notes": architecture_notes,
            "recent_tool_outputs": recent_outputs,
            "execution_history": execution_history,
            "callers": callers,
            "callees": callees,
            "runtime_memory": {
                "iterations": state.runtime_memory.total_iterations if getattr(state, "runtime_memory", None) else 0,
                "tool_calls": state.runtime_memory.tool_call_count if getattr(state, "runtime_memory", None) else 0,
                "retrievals": state.runtime_memory.retrieval_count if getattr(state, "runtime_memory", None) else 0,
                "repairs": state.runtime_memory.repair_count if getattr(state, "runtime_memory", None) else 0,
                "runtime_errors": state.runtime_memory.runtime_errors if getattr(state, "runtime_memory", None) else []
            },
            "loop_warning": self.detect_loops(state)
        }

    def detect_loops(self, state: TaskState):
        recent = state.completed_steps[-6:] if getattr(state, "completed_steps", None) else []
        if len(recent) < 6:
            return False
        unique = len(set(recent))
        return unique <= 2
