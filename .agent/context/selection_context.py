# context/selection_context.py

"""Utility to build minimal selection‑centric context for fast‑edit paths.
It extracts the selected code span, a few surrounding lines, and basic metadata
without any repository‑wide DB lookups.
"""

from runtime.editor.models import EditorState
from repository.file_manager import FileManager


class SelectionContextBuilder:
    """Builds a lightweight context focused on the current editor selection.

    The returned dict contains:
        - selected_code: the exact code the user selected.
        - surrounding: up to 5 lines before and after the selection.
        - parent_symbol: placeholder (could be enhanced with AST analysis).
        - imports: placeholder list of import statements in the file.
    """

    @staticmethod
    def build(editor_state: EditorState) -> dict | None:
        if not editor_state or not editor_state.active_file:
            return None
        # Resolve file content via FileManager
        fm = FileManager(root=".")
        try:
            content = fm.read_file(editor_state.active_file)
        except Exception:
            return None
        lines = content.splitlines()
        # Determine selection range (line numbers are 1‑based)
        sel_range = getattr(editor_state, "selection_range", None)
        if not sel_range:
            return None
        (start_line, _), (end_line, _) = sel_range
        # Clamp indices
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        selected_code = "\n".join(lines[start_idx:end_idx])
        # Surrounding context (5 lines before and after)
        surrounding_before = lines[max(0, start_idx - 5): start_idx]
        surrounding_after = lines[end_idx: min(len(lines), end_idx + 5)]
        surrounding = "\n".join(surrounding_before + surrounding_after)
        # Simple import extraction (lines starting with 'import' or 'from')
        imports = [ln for ln in lines if ln.lstrip().startswith("import ") or ln.lstrip().startswith("from ")]
        return {
            "selected_code": selected_code,
            "surrounding": surrounding,
            "parent_symbol": None,  # Future AST‑based lookup could fill this
            "imports": imports,
        }
