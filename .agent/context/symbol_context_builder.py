# context/symbol_context_builder.py
"""Symbol‑Context Builder

Provides a lightweight context for edits that reference a specific symbol.
It extracts the symbol definition and a small number of callers/callees
without traversing the full repository graph, keeping latency within the
20‑50 ms budget.
"""

from typing import Optional, List, Dict

from repository.file_manager import FileManager

from retrieval.symbol_graph_cache import SymbolGraphCache
from runtime.editor.models import EditorState


class SymbolContextBuilder:
    """Build minimal symbol‑centric context.

    The builder returns a dictionary containing:
        * ``definition`` – the source snippet for the target symbol.
        * ``callers`` – up to two caller snippets.
        * ``callees`` – up to two callee snippets.
    It purposefully avoids heavy graph expansion.
    """

    @staticmethod
    def _extract_snippet(file_path: str, start_line: int, end_line: int) -> str:
        """Read the file and return the source code for the given line range."""
        fm = FileManager(root=".")
        try:
            content = fm.read_file(file_path)
        except Exception:
            return ""
        lines = content.splitlines()
        # Convert 1‑based indices to list slices
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        return "\n".join(lines[start_idx:end_idx])

    @staticmethod
    def build(symbol_name: str) -> Optional[Dict[str, any]]:
        """Return a lightweight context dict for *symbol_name*.

        Parameters
        ----------
        symbol_name: str
            Fully qualified name (e.g. ``MyClass.my_method``).
        """
        cache = SymbolGraphCache.get_instance()
        # Resolve the symbol by qualified name
        sym_record = cache.get_symbol_by_qualified_name(symbol_name)
        if not sym_record:
            return None

        symbol_id = sym_record["id"]
        file_path = sym_record["file_path"]
        start_line = sym_record["start_line"]
        end_line = sym_record["end_line"]

        definition = SymbolContextBuilder._extract_snippet(file_path, start_line, end_line)

        # Callers – limit to first two
        callers_raw = cache.get_callers(symbol_id)[:2]
        callers: List[str] = []
        for c in callers_raw:
            callers.append(SymbolContextBuilder._extract_snippet(
                c["file_path"], c["start_line"], c["end_line"]
            ))

        # Callees – limit to first two
        callees_raw = cache.get_callees(symbol_id)[:2]
        callees: List[str] = []
        for c in callees_raw:
            callees.append(SymbolContextBuilder._extract_snippet(
                c["file_path"], c["start_line"], c["end_line"]
            ))

        return {
            "symbol_name": symbol_name,
            "definition": definition,
            "callers": callers,
            "callees": callees,
        }
