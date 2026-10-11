# context/context_budget.py
"""
Context Budget — hard token limits for each tier.

Optimised for local 3B–7B LLMs where context quality > context quantity.

Tiers
-----
HOT  (<2 000 tokens) — always included, never pruned
WARM (<6 000 tokens) — included when budget allows
COLD (<4 000 tokens) — lazy, only when explicitly requested

Total hard cap per mode:
  inline  :  2 000
  patch   :  8 000
  assist  :  8 000
  agent   : 12 000
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Tier token caps
# ---------------------------------------------------------------------------
HOT_TOKENS  = 2_000    # active buffer + cursor + diagnostics + primary symbol
WARM_TOKENS = 6_000    # dependent symbols + imports + graph neighbours
COLD_TOKENS = 4_000    # retrieval memory, history, reflections (lazy)

# Total hard caps per mode
MODE_CAPS: dict[str, int] = {
    "inline"      : 2_000,
    "inline_edit" : 2_000,
    "patch"       : 8_000,
    "patch_edit"  : 8_000,
    "assist"      : 8_000,
    "code_assist" : 8_000,
    "agent"       : 12_000,
    "agent_deep"  : 16_000,   # explicit deep mode — rare
}

# Keys that belong to COLD tier — dropped first when over budget
COLD_KEYS: frozenset = frozenset({
    "reflections",
    "repair_history",
    "execution_history",
    "failed_steps",
    "recent_tool_outputs",
    "architecture_notes",
    "generated_code",
    "test_failures",
})

# Keys that belong to WARM tier — dropped after COLD when still over budget
WARM_KEYS: frozenset = frozenset({
    "retrieved_chunks",
    "callers",
    "callees",
    "modification_targets",
    "modified_files",
    "touched_files",
    "current_plan",
    "pending_executions",
})


class ContextBudget:
    HOT_TOKENS  = HOT_TOKENS
    WARM_TOKENS = WARM_TOKENS
    COLD_TOKENS = COLD_TOKENS

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(val: Any) -> int:
        """Fast token estimate: len(str(val)) / 4 (chars-per-token heuristic)."""
        return max(1, len(str(val)) // 4)

    @classmethod
    def estimate_tokens_total(cls, ctx: dict) -> int:
        """Estimate total token count of the entire assembled context dict."""
        return sum(cls.estimate_tokens(v) for v in ctx.values())

    # ------------------------------------------------------------------
    # Per-tier enforcers
    # ------------------------------------------------------------------

    @classmethod
    def enforce_hot(cls, hot_data: dict) -> dict:
        """Trim HOT data to stay under HOT_TOKENS."""
        while cls.estimate_tokens(hot_data) > cls.HOT_TOKENS:
            sel = hot_data.get("selection", "")
            if len(sel) > 200:
                hot_data["selection"] = sel[: len(sel) // 2] + "\n... [HOT budget: truncated]"
            else:
                break
        return hot_data

    @classmethod
    def enforce_warm(cls, warm_data: dict) -> dict:
        """Trim WARM data: drop retrieved_symbols tail-first."""
        symbols = warm_data.get("retrieved_symbols", [])
        while symbols and cls.estimate_tokens(warm_data) > cls.WARM_TOKENS:
            symbols.pop()
        warm_data["retrieved_symbols"] = symbols
        return warm_data

    @classmethod
    def enforce_cold(cls, cold_data: dict) -> dict:
        """Trim COLD data: drop list items from the least-important keys first."""
        drop_order = [
            "execution_history", "recent_tool_outputs", "reflections",
            "failed_steps", "repair_history", "architecture_notes",
            "generated_code", "test_failures",
        ]
        for key in drop_order:
            items = cold_data.get(key, [])
            while items and cls.estimate_tokens(cold_data) > cls.COLD_TOKENS:
                if isinstance(items, list):
                    items.pop()
                else:
                    cold_data[key] = None
                    break
        return cold_data

    # ------------------------------------------------------------------
    # Total budget enforcer (called AFTER full assembly)
    # ------------------------------------------------------------------

    @classmethod
    def enforce_total_budget(cls, ctx: dict, mode: str = "agent") -> dict:
        """Drop keys tier-by-tier until ctx fits within the mode's hard cap.

        Drop order: COLD keys first → WARM keys second → truncate HOT last.
        """
        cap = MODE_CAPS.get(mode.lower(), 12_000)
        if cls.estimate_tokens_total(ctx) <= cap:
            return ctx

        # Stage 1: drop COLD keys entirely
        for key in COLD_KEYS:
            if cls.estimate_tokens_total(ctx) <= cap:
                break
            if key in ctx and ctx[key]:
                ctx[key] = [] if isinstance(ctx[key], list) else None

        if cls.estimate_tokens_total(ctx) <= cap:
            return ctx

        # Stage 2: trim WARM list keys (drop tail items)
        for key in WARM_KEYS:
            if cls.estimate_tokens_total(ctx) <= cap:
                break
            items = ctx.get(key)
            if isinstance(items, list):
                while items and cls.estimate_tokens_total(ctx) > cap:
                    items.pop()

        if cls.estimate_tokens_total(ctx) <= cap:
            return ctx

        # Stage 3: truncate goal / plan strings (last resort)
        for key in ("current_plan", "goal"):
            val = ctx.get(key, "")
            if isinstance(val, str) and len(val) > 200:
                ctx[key] = val[:200] + "... [budget: truncated]"
            if cls.estimate_tokens_total(ctx) <= cap:
                break

        return ctx
