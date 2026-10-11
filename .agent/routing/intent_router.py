# routing/intent_router.py

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Any

# Import ContextBuilderEnum to specify both execution and context modes
from context.context_router import ContextBuilderEnum

from core.execution_mode import TaskIntentMode as ExecutionMode

# Backward compatibility aliases
ExecutionMode.INLINE_EDIT = ExecutionMode.INLINE
ExecutionMode.PATCH_EDIT = ExecutionMode.PATCH
ExecutionMode.MULTI_FILE_PATCH = ExecutionMode.AGENT
ExecutionMode.FAST_COMPLETION = ExecutionMode.INLINE
ExecutionMode.FAST_EDIT = ExecutionMode.PATCH
ExecutionMode.CODE_ASSIST = ExecutionMode.ASSIST
ExecutionMode.SMART_EDIT = ExecutionMode.PATCH
ExecutionMode.AUTONOMOUS_AGENT = ExecutionMode.AGENT

class CostTier(str, Enum):
    CHEAP = "cheap"
    MEDIUM = "medium"
    EXPENSIVE = "expensive"

@dataclass
class RouteDecision:
    execution_mode: ExecutionMode
    context_mode: ContextBuilderEnum
    confidence: float
    reason: str
    cost_tier: CostTier

    @property
    def mode(self) -> ExecutionMode:
        """Backward compatibility property for orchestrator/tests expecting `decision.mode`."""
        return self.execution_mode

class IntentRouter:
    
    @staticmethod
    def _llm_route(query: str, editor_context: Optional[Any] = None) -> Optional[RouteDecision]:
        try:
            from llm.ollama_client import OllamaClient
            from inference.router import TaskType
            import json

            # Gather context info to pass to the LLM
            has_selection = False
            selection_len = 0
            if editor_context:
                selected_text = getattr(editor_context, "selected_text", None) or getattr(editor_context, "selection", None)
                if selected_text:
                    has_selection = True
                    selection_len = len(selected_text.splitlines())

            system_prompt = """You are a router that classifies developer query intent into execution and context modes.

Available execution modes:
- "inline_edit": Smallest, fastest changes (like autocompleting a line, adding a docstring, renaming a variable, simple text additions).
- "patch_edit": Local editing of a single file, e.g., modifying a function or class.
- "multi_file_patch": Changes spanning multiple files or packages.
- "agent": Complex tasks, explaining architecture, search across repo, running tests.

Available context modes:
- "selection": Active selection/cursor window only.
- "symbol": Target symbol info (definition, inputs, outputs).
- "repository": Entire package/module callers, callees, dependencies.
- "agent": All context layers, history, plans.

Available cost tiers:
- "cheap": Simple edits or inline completions.
- "medium": Single or multi-file edits.
- "expensive": Full agent search, explanations, and test repairs.

Respond ONLY with a JSON object in this format:
{
  "execution_mode": "inline_edit" | "patch_edit" | "multi_file_patch" | "agent",
  "context_mode": "selection" | "symbol" | "repository" | "agent",
  "confidence": float (0.0 to 1.0),
  "reason": "one sentence explaining classification",
  "cost_tier": "cheap" | "medium" | "expensive"
}"""

            user_prompt = f"""USER QUERY: {query}
HAS ACTIVE SELECTION: {has_selection}
SELECTION LENGTH: {selection_len} lines"""

            # Call client using TaskType.RETRIEVAL to route to the 1-3B model tier
            client = OllamaClient()
            response = client.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], task_type=TaskType.RETRIEVAL)

            # Clean response and extract JSON block safely
            cleaned = response.strip()
            import re
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)

            parsed = json.loads(cleaned)

            # Parse strings to corresponding enums
            from context.context_router import ContextBuilderEnum
            
            exec_mode_str = parsed["execution_mode"].lower().strip()
            # Map legacy/agent names to patch values for pure Cursor execution
            mapping = {
                "inline_edit": "inline",
                "patch_edit": "patch",
                "multi_file_patch": "patch",
                "smart_edit": "patch",
                "autonomous_agent": "patch",
                "code_assist": "patch",
                "assist": "assist",
                "inline": "inline",
                "patch": "patch",
                "agent": "patch",
                "analyze": "analyze",
                "review": "analyze",
                "audit": "analyze"
            }
            exec_mode_str = mapping.get(exec_mode_str, exec_mode_str)
            
            context_mode_str = parsed["context_mode"].lower().strip()
            if context_mode_str == "agent":
                context_mode_str = "repository"
            cost_tier_str = parsed["cost_tier"].lower().strip()

            valid_execs = {
                "inline": ExecutionMode.INLINE,
                "patch": ExecutionMode.PATCH,
                "assist": ExecutionMode.ASSIST,
                "agent": ExecutionMode.PATCH,
                "analyze": ExecutionMode.ANALYZE,
                0: ExecutionMode.INLINE,
                1: ExecutionMode.PATCH,
                2: ExecutionMode.ASSIST,
                3: ExecutionMode.PATCH,
                4: ExecutionMode.ANALYZE
            }
            valid_contexts = {c.value: c for c in ContextBuilderEnum}
            valid_costs = {t.value: t for t in CostTier}

            if exec_mode_str in valid_execs and context_mode_str in valid_contexts and cost_tier_str in valid_costs:
                return RouteDecision(
                    execution_mode=valid_execs[exec_mode_str],
                    context_mode=valid_contexts[context_mode_str],
                    confidence=float(parsed.get("confidence", 0.9)),
                    reason=str(parsed.get("reason", "LLM classified intent")),
                    cost_tier=valid_costs[cost_tier_str]
                )
        except Exception as e:
            # Fallback gracefully
            print(f"[IntentRouter] Warning: LLM classification failed ({e}). Falling back to heuristics.")
            return None

    @staticmethod
    def route(query: str, editor_context: Optional[Any] = None, bypass_llm: bool = False) -> RouteDecision:
        # Check active selection / editor context first for Cursor-like fast path routing
        if editor_context:
            selected_text = getattr(editor_context, "selected_text", None) or getattr(editor_context, "selection", None)
            diagnostics = getattr(editor_context, "diagnostics", [])
            if selected_text and not diagnostics:
                return RouteDecision(
                    execution_mode=ExecutionMode.INLINE,
                    context_mode=ContextBuilderEnum.SELECTION,
                    confidence=0.98,
                    reason="Cursor-like fast route: active selection present.",
                    cost_tier=CostTier.CHEAP,
                )

            active_file = getattr(editor_context, "active_file", None)
            has_explain = any(x in query.lower() for x in ["explain", "what is", "how does", "describe", "summarize"])
            if active_file and len(query.split()) < 15 and not has_explain:
                return RouteDecision(
                    execution_mode=ExecutionMode.PATCH,
                    context_mode=ContextBuilderEnum.SELECTION,
                    confidence=0.95,
                    reason="Cursor-like fast route: active file with short prompt.",
                    cost_tier=CostTier.CHEAP,
                )

        # Fast path heuristic check for pure analysis/explain queries (bypasses LLM classifier)
        q_lower = query.lower()
        analysis_verbs = {
            "explain", "what is", "how does", "summarize", "tell me about",
            "where is", "search for", "find symbol", "analyze", "analyse", "understand",
            "check", "show", "inspect", "read", "view", "find",
            "list", "audit", "review", "scan", "report", "go through", "get issues", "find issues"
        }
        modify_keywords = {
            "fix", "change", "add", "modify", "update", "implement", "write", "create", "delete", "remove", "refactor", "rename"
        }
        has_analysis = any(verb in q_lower for verb in analysis_verbs)
        has_modify = any(mod in q_lower for mod in modify_keywords)
        if has_analysis and not has_modify:
            is_analyze = any(w in q_lower for w in ["review", "audit", "analyse", "analyze", "find issues", "look for bugs", "get issues"])
            return RouteDecision(
                execution_mode=ExecutionMode.ANALYZE if is_analyze else ExecutionMode.ASSIST,
                context_mode=ContextBuilderEnum.REPOSITORY,
                confidence=0.98,
                reason="Fast-path heuristic: pure analysis/explain query.",
                cost_tier=CostTier.CHEAP
            )

        # Try first-pass classification using a small fast model
        if not bypass_llm:
            decision = IntentRouter._llm_route(query, editor_context)
            if decision is not None:
                # Force to INLINE if selection exists and mode is ASSIST
                has_selection = False
                if editor_context:
                    selected_text = getattr(editor_context, "selected_text", None) or getattr(editor_context, "selection", None)
                    if selected_text:
                        has_selection = True
                if has_selection and decision.execution_mode == ExecutionMode.ASSIST:
                    decision.execution_mode = ExecutionMode.INLINE
                    decision.context_mode = ContextBuilderEnum.SELECTION
                return decision

        q = query.lower()
        
        # Check active selection
        has_selection = False
        is_very_short_selection = False
        if editor_context:
            selected_text = getattr(editor_context, "selected_text", None) or getattr(editor_context, "selection", None)
            if selected_text:
                has_selection = True
                if len(selected_text.splitlines()) < 20:
                    is_very_short_selection = True

        # Check symbol mentions in query
        import re
        symbol_regex = re.compile(r"\b\w+\.\w+\b")
        func_call_regex = re.compile(r"\b\w+\s*\(")
        has_symbol_mention = bool(symbol_regex.search(query) or func_call_regex.search(query))

        # Check repository-wide work keywords
        repo_keywords = [
            "refactor", "module", "package", "dependency", "import", "file",
            "cross-file", "across files", "multiple files", "rename class", "rename method"
        ]
        has_repo_keywords = any(kw in q for kw in repo_keywords)

        # 1. INLINE Heuristics (Autocomplete, docstrings, short edits, explain selection)
        inline_keywords = ["autocomplete", "continue this", "inline suggest", "complete signature", "generate docstring"]
        is_inline_pattern = any(x in q for x in inline_keywords)
        
        assist_keywords = ["explain", "what is", "how does", "summarize", "tell me about", "where is", "search for", "find symbol", "analyze", "analyse", "understand", "check", "show", "inspect", "read", "view", "find", "list", "audit", "review", "scan", "report", "go through", "get issues", "find issues"]
        modify_keywords = ["fix", "change", "add", "modify", "update", "implement", "write", "create", "delete", "remove", "refactor", "rename"]
        
        has_assist = any(x in q for x in assist_keywords)
        has_modify = any(x in q for x in modify_keywords)

        # Route explain query with active selection straight to INLINE mode (bypassing planner & retrieval)
        if (has_selection and has_assist) or is_inline_pattern or (is_very_short_selection and any(x in q for x in ["fill", "write boilerplate", "finish"])):
            return RouteDecision(
                execution_mode=ExecutionMode.INLINE,
                context_mode=ContextBuilderEnum.SELECTION,
                confidence=0.95,
                reason="Match inline request with active selection.",
                cost_tier=CostTier.CHEAP
            )

        # Heavy agent keywords
        agent_keywords = ["build a", "create sub-system", "migrate", "massive refactor", "system rewrite", "across multiple files"]
        has_heavy_agent = any(x in q for x in agent_keywords)

        # 2. PATCH (Single-file / local edits)
        if has_modify and not has_heavy_agent and not has_repo_keywords:
            context_mode = ContextBuilderEnum.SYMBOL if has_symbol_mention else ContextBuilderEnum.SELECTION
            return RouteDecision(
                execution_mode=ExecutionMode.PATCH,
                context_mode=context_mode,
                confidence=0.90,
                reason="Local modification request targeting single file or active context.",
                cost_tier=CostTier.MEDIUM
            )

        # 3. MULTI_FILE_PATCH (Refactoring/renaming across modules -> routes to PATCH mode)
        if has_modify and has_repo_keywords and not has_heavy_agent:
            return RouteDecision(
                execution_mode=ExecutionMode.PATCH,
                context_mode=ContextBuilderEnum.REPOSITORY,
                confidence=0.90,
                reason="Modification request spanning multiple files or modules.",
                cost_tier=CostTier.MEDIUM
            )

        # 4. ASSIST / ANALYZE (Read-only search/explanation across project without modifications)
        if (has_assist or not has_modify) and not has_modify:
            is_analyze = any(w in q for w in ["review", "audit", "analyse", "analyze", "find issues", "look for bugs", "get issues"])
            return RouteDecision(
                execution_mode=ExecutionMode.ANALYZE if is_analyze else ExecutionMode.ASSIST,
                context_mode=ContextBuilderEnum.REPOSITORY,
                confidence=0.90,
                reason="Assist/Analyze request with no modification verb.",
                cost_tier=CostTier.CHEAP
            )
            
        # Fallback routing based on ComplexityEstimator score
        from routing.complexity_estimator import ComplexityEstimator
        score = ComplexityEstimator.estimate(query, editor_context)

        if score < 0.25:
            return RouteDecision(
                execution_mode=ExecutionMode.INLINE,
                context_mode=ContextBuilderEnum.SELECTION,
                confidence=0.90,
                reason=f"Low complexity score ({score:.2f}) -> INLINE fallback.",
                cost_tier=CostTier.CHEAP
            )
        elif score < 0.45:
            return RouteDecision(
                execution_mode=ExecutionMode.PATCH,
                context_mode=ContextBuilderEnum.SELECTION,
                confidence=0.90,
                reason=f"Medium complexity score ({score:.2f}) -> PATCH fallback.",
                cost_tier=CostTier.MEDIUM
            )
        else:
            return RouteDecision(
                execution_mode=ExecutionMode.ASSIST,
                context_mode=ContextBuilderEnum.REPOSITORY,
                confidence=0.90,
                reason=f"High complexity score ({score:.2f}) -> ASSIST fallback.",
                cost_tier=CostTier.MEDIUM
            )
