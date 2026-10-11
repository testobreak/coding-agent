# context/selection_context_builder.py
"""Selection‑Context Builder

Provides the minimal context required for fast‑edit operations based on the
current editor selection. Returns a plain dictionary that can be fed to the
fast‑edit pipeline.
"""

from runtime.editor.models import EditorState
from repository.file_manager import FileManager

class SelectionContextBuilder:
    """Build a lightweight context focusing on the current selection.

    The builder extracts the selected snippet, a few surrounding lines, and a
    list of import statements from the active file. No repository‑wide lookups
    are performed, keeping latency within the 10‑20 ms budget.
    """

    @staticmethod
    def build(editor_state: EditorState) -> dict | None:
        """Return a context dict or ``None`` when insufficient information.

        Parameters
        ----------
        editor_state: EditorState
            Must contain ``active_file`` and ``selection_range``.
        """
        if not editor_state or not editor_state.active_file:
            return None

        fm = FileManager(root=".")
        try:
            content = fm.read_file(editor_state.active_file)
        except Exception:
            return None

        lines = content.splitlines()
        sel_range = getattr(editor_state, "selection_range", None)
        if not sel_range:
            return None
        (start_line, _), (end_line, _) = sel_range
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        selected_code = "\n".join(lines[start_idx:end_idx])

        # Surrounding context – up to 5 lines before and after the selection
        surrounding_before = lines[max(0, start_idx - 5): start_idx]
        surrounding_after = lines[end_idx: min(len(lines), end_idx + 5)]
        surrounding = "\n".join(surrounding_before + surrounding_after)

        # Simple import extraction
        imports = [ln for ln in lines if ln.lstrip().startswith("import ") or ln.lstrip().startswith("from ")]

        return {
            "selected_code": selected_code,
            "surrounding": surrounding,
            "parent_symbol": None,  # Placeholder for future AST‑based lookup
            "imports": imports,
        }
