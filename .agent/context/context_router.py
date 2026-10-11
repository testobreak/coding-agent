# context/context_router.py
"""Context Router

Selects the appropriate context builder based on the editor state and the
user request. The router enables the new modular ContextEngine architecture.
"""

import re
from enum import Enum
from typing import Optional

from runtime.editor.models import EditorState


class ContextBuilderEnum(Enum):
    SELECTION = "selection"
    SYMBOL = "symbol"
    REPOSITORY = "repository"
    AGENT = "agent"


class ContextRouter:
    """Choose a context builder for a given request.

    Heuristics (ordered by priority):
    1. **Selection** – if the editor state provides a non‑empty selection_range.
    2. **Symbol** – if the request mentions a symbol using dot notation
       (e.g., ``Class.method``) or a function call pattern ``func_name(``.
    3. **Repository** – if the request contains keywords that imply cross‑file
       work (e.g., "refactor", "module", "dependency", "import", "file").
    4. **Agent** – fallback for complex autonomous tasks.
    """

    # Simple keyword sets for heuristic detection
    _REPO_KEYWORDS = {
        "refactor",
        "module",
        "package",
        "dependency",
        "import",
        "file",
        "cross‑file",
        "across files",
        "multiple files",
        "rename",
        "move",
    }

    _SYMBOL_REGEX = re.compile(r"\b\w+\.\w+\b")  # e.g., Class.method
    _FUNC_CALL_REGEX = re.compile(r"\b\w+\s*\(")   # e.g., func(

    @staticmethod
    def choose_builder(request: str, editor_state: Optional[EditorState] = None) -> ContextBuilderEnum:
        """Return the most suitable builder enum.

        Parameters
        ----------
        request: str
            The raw user query.
        editor_state: Optional[EditorState]
            Provides selection, cursor, and active file information.
        """
        # 1️⃣ Selection path – requires a concrete selection range
        if editor_state:
            sel_range = getattr(editor_state, "selection_range", None)
            if sel_range:
                # Ensure the range contains at least one line
                try:
                    (s_line, _), (e_line, _) = sel_range
                    if e_line >= s_line:
                        return ContextBuilderEnum.SELECTION
                except Exception:
                    pass

        # 2️⃣ Symbol detection in the request text
        if ContextRouter._SYMBOL_REGEX.search(request) or ContextRouter._FUNC_CALL_REGEX.search(request):
            return ContextBuilderEnum.SYMBOL

        # 3️⃣ Repository‑wide hints
        lower_req = request.lower()
        if any(keyword in lower_req for keyword in ContextRouter._REPO_KEYWORDS):
            return ContextBuilderEnum.REPOSITORY

        # 4️⃣ Default to the heavy agent builder
        return ContextBuilderEnum.AGENT
