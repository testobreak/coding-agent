# context/policy_engine.py

from dataclasses import dataclass, field
from typing import Optional, Set

@dataclass
class ContextPolicy:
    allowed_keys: Set[str] = field(default_factory=set) # Whitelisted memory domain keys allowed to be included
    token_budget: int = 40000               # Strict hard token budget limit
    materialization_limit: int = 0  # Number of RAG chunks to resolve / materialize content for
    include_local_symbol: bool = True
    include_repo_context: bool = True
    include_ui_context: bool = True
    include_memory: bool = True

class ContextPolicyEngine:
    @staticmethod
    def choose_context(goal: str, mode: Optional[str] = None) -> ContextPolicy:
        """
        Retrieves the whitelisting rules, token budgets, and materialization limits
        for the given execution mode or goal string.
        """
        # Normalize mode string
        m = (mode or "").lower().strip()

        # 1. INLINE mode: simple completions, active selection/buffer only
        if m in ("inline_edit", "inline", "fast_completion"):
            return ContextPolicy(
                allowed_keys={"editor_state", "diagnostics"},
                token_budget=4000,
                materialization_limit=0
            )

        # 2. PATCH mode: local/single file editing
        elif m in ("patch_edit", "patch"):
            return ContextPolicy(
                allowed_keys={
                    "editor_state",
                    "diagnostics",
                    "active_targets",
                    "retrieved_symbols"
                },
                token_budget=12000,
                materialization_limit=2
            )

        # 3. ASSIST mode: read-only architecture exploration / explanation
        elif m in ("code_assist", "assist"):
            return ContextPolicy(
                allowed_keys={
                    "editor_state",
                    "diagnostics",
                    "active_targets",
                    "retrieved_symbols",
                    "dependency_neighbors"
                },
                token_budget=12000,
                materialization_limit=10
            )

        # 4. Fallback heuristics if mode is not explicitly passed
        g_lower = goal.lower()
        assist_keywords = ["explain", "why", "how", "describe", "understand", "what", "where", "summarize"]
        edit_keywords = ["edit", "patch", "modify", "add", "change", "delete", "remove", "implement", "rename", "fix"]
        
        is_assist = any(kw in g_lower for kw in assist_keywords)
        is_edit = any(kw in g_lower for kw in edit_keywords)

        if is_assist and not is_edit:
            return ContextPolicy(
                allowed_keys={
                    "editor_state",
                    "diagnostics",
                    "active_targets",
                    "retrieved_symbols",
                    "dependency_neighbors"
                },
                token_budget=12000,
                materialization_limit=10
            )
        elif is_edit:
            # Route to PATCH mode equivalent policy
            return ContextPolicy(
                allowed_keys={
                    "editor_state",
                    "diagnostics",
                    "active_targets",
                    "retrieved_symbols"
                },
                token_budget=12000,
                materialization_limit=2
            )

        # 5. AGENT mode: default policy with access to all domains under 40k token budget
        return ContextPolicy(
            allowed_keys={
                "editor_state",
                "diagnostics",
                "active_targets",
                "retrieved_symbols",
                "dependency_neighbors",
                "patch_candidates",
                "episodic_summaries",
                "failed_attempts",
                "reflections",
                "tool_outputs",
                "raw_logs"
            },
            token_budget=40000,
            materialization_limit=20
        )

    @staticmethod
    def get_budget(mode: str) -> dict:
        """
        Legacy helper for compatibility with other subsystems.
        """
        m = (mode or "").lower().strip()
        if "inline" in m:
            return {"tier1": 1800, "tier2": 500, "tier3": 0}
        elif "patch" in m:
            return {"tier1": 1800, "tier2": 2500, "tier3": 1500}
        elif "assist" in m:
            return {"tier1": 1800, "tier2": 2500, "tier3": 1500}
        else:
            return {"tier1": 2000, "tier2": 4000, "tier3": 6000}

    @staticmethod
    def is_firewalled(mode: str) -> bool:
        """
        Legacy helper for compatibility.
        """
        m = (mode or "").lower().strip()
        return "inline" in m or "patch" in m or "assist" in m
