# runtime/fast_path_router.py

"""Fast path router to decide between fast edit and autonomous agent modes.
It examines the query and the editor state (selection, active file) and returns a
RouteDecision specifying both execution and context modes.
"""

from routing.intent_router import ExecutionMode, CostTier, RouteDecision
from context.context_router import ContextBuilderEnum
from runtime.editor.models import EditorState


class FastPathRouter:
    """Stateless router that decides if a request can be handled by the fast edit engine."""

    FAST_EDIT_KEYWORDS = [
        "rename",
        "add",
        "remove",
        "delete",
        "log",
        "print",
        "comment",
        "docstring",
        "explain",
        "refactor",
        "optimize",
        "fix",
        "update",
    ]

    @staticmethod
    def route(query: str, editor_state: EditorState | None = None) -> RouteDecision:
        q = query.lower()
        # Fast edit if we have an active selection or active file and simple verbs
        has_selection = False
        if editor_state:
            sel = getattr(editor_state, "selection_range", None) or getattr(editor_state, "selected_text", None)
            if sel:
                has_selection = True
        keyword_match = any(kw in q for kw in FastPathRouter.FAST_EDIT_KEYWORDS)

        if has_selection and keyword_match:
            return RouteDecision(
                execution_mode=ExecutionMode.PATCH_EDIT,
                context_mode=ContextBuilderEnum.SELECTION,
                confidence=0.95,
                reason="Simple edit intent with selection and fast‑edit keywords.",
                cost_tier=CostTier.CHEAP,
            )
        # Fallback to original IntentRouter logic (delegated)
        from routing.intent_router import IntentRouter

        return IntentRouter.route(query, editor_context=editor_state)
