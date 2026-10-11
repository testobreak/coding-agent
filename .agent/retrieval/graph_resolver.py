# retrieval/graph_resolver.py
#
# Graph Execution Engine — translates a ResolutionPlan(mode=GRAPH) into a
# ranked list of chunk-compatible dicts using the in-memory SymbolGraphCache.
#
# No ANN. No pgvector. Pure graph traversal at 1-5 ms.
#
# Supported graph operations (graph_op field in ResolutionPlan):
#
#   callers    — symbols that call the target
#   callees    — symbols called by the target
#   deps       — direct dependencies (USES / INHERITS / IMPLEMENTS)
#   impls      — concrete implementations of the target interface
#   interfaces — interfaces/supertypes that the target implements
#   related    — USES / DEPENDS relationships of the target

from __future__ import annotations

import os
import time
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from retrieval.query_resolver import ResolutionPlan


# Score assigned to graph-resolved candidates.
# High but not 1.0 — leaves room for span-matched SYMBOL route to rank higher.
_GRAPH_CANDIDATE_SCORE = 0.90

# Score for secondary graph expansion (e.g. transitive deps, test files)
_GRAPH_SECONDARY_SCORE = 0.65


class GraphResolver:
    """
    Translates a ResolutionPlan with mode=GRAPH into a list of chunk-compatible
    dicts ready for context assembly and LLM consumption.

    Each returned dict has the standard chunk schema:
      chunk_id, name, symbol, file, start_line, end_line, code, score
    """

    def resolve(self, plan: "ResolutionPlan", top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Execute graph traversal for the given plan.

        Args:
            plan:   ResolutionPlan with mode=GRAPH.
            top_k:  Maximum number of candidates to return.

        Returns:
            List of chunk-compatible dicts sorted by relevance score.
        """
        start = time.time()

        from retrieval.symbol_graph_cache import SymbolGraphCache
        cache = SymbolGraphCache.get_instance()

        if not cache.is_loaded:
            cache.load()

        if not cache.is_loaded:
            print("[GraphResolver] SymbolGraphCache not available — no results")
            return []

        graph_op = plan.graph_op or "related"
        primary_symbols = plan.symbols  # already-resolved dicts from QueryResolver

        # If no symbols were resolved (query had structural pattern but no known symbol),
        # attempt a best-effort name search from the query tokens.
        if not primary_symbols and plan.symbol_names:
            for name in plan.symbol_names:
                matches = cache.get_symbols_by_name(name)
                primary_symbols.extend(matches)
                if primary_symbols:
                    break

        if not primary_symbols:
            print(f"[GraphResolver] No symbols for graph_op='{graph_op}' — empty result")
            return []

        # ── Traverse graph for each primary symbol ──────────────────────────
        result_symbols: List[dict] = []
        seen_ids = set()

        for sym in primary_symbols:
            sym_id = sym.get("id")
            if not sym_id:
                continue

            traversed = self._traverse(cache, sym_id, graph_op)
            for ts in traversed:
                ts_id = ts.get("id")
                if ts_id and ts_id not in seen_ids:
                    seen_ids.add(ts_id)
                    result_symbols.append(ts)

        # Include primary symbols themselves as context anchors
        for sym in primary_symbols:
            sym_id = sym.get("id")
            if sym_id and sym_id not in seen_ids:
                seen_ids.add(sym_id)
                result_symbols.insert(0, sym)  # primary first

        if not result_symbols:
            print(f"[GraphResolver] Graph traversal returned 0 symbols for op='{graph_op}'")
            return []

        # ── Convert to chunk-compatible dicts ──────────────────────────────
        chunks = []
        for i, sym in enumerate(result_symbols[:top_k]):
            score = _GRAPH_CANDIDATE_SCORE if i < len(primary_symbols) else _GRAPH_SECONDARY_SCORE
            chunk = self._sym_to_chunk(sym, score)
            if chunk:
                chunks.append(chunk)

        elapsed = time.time() - start
        print(
            f"[GraphResolver] graph_op='{graph_op}' resolved {len(chunks)} candidates "
            f"in {elapsed * 1000:.1f}ms (no ANN)"
        )
        return chunks

    # ── Graph Operation Dispatch ────────────────────────────────────────────

    def _traverse(self, cache, sym_id: str, graph_op: str) -> List[dict]:
        """Dispatch the graph_op to the appropriate SymbolGraphCache method."""
        op_map = {
            "callers":    cache.get_callers,
            "callees":    cache.get_callees,
            "deps":       cache.get_dependencies,
            "impls":      cache.get_implementations,
            "interfaces": cache.get_interfaces,
            "related":    cache.get_related_symbols,
        }
        fn = op_map.get(graph_op)
        if fn is None:
            # Unknown op — return empty, will fall through to semantic
            print(f"[GraphResolver] Unknown graph_op='{graph_op}'")
            return []
        try:
            return fn(sym_id) or []
        except Exception as e:
            print(f"[GraphResolver] Graph traversal error (op={graph_op}): {e}")
            return []

    # ── Symbol → Chunk Conversion ───────────────────────────────────────────

    def _sym_to_chunk(self, sym: dict, score: float) -> Dict[str, Any] | None:
        """
        Convert a SymbolGraphCache symbol dict to a chunk-compatible dict
        that downstream context assembler and LLM prompts can consume.
        """
        file_path = sym.get("file_path") or ""
        name = sym.get("name") or ""
        qualified_name = sym.get("qualified_name") or name
        start_line = sym.get("start_line") or 1
        end_line = sym.get("end_line") or start_line
        sym_type = sym.get("symbol_type") or "unknown"
        signature = sym.get("signature") or ""

        if not file_path:
            return None

        # Attempt to read actual source lines for richer context
        source_snippet = self._read_source_span(file_path, start_line, end_line)

        return {
            "chunk_id":   f"graph:{qualified_name}",
            "name":       name,
            "symbol":     qualified_name,
            "symbol_path": qualified_name,
            "type":       sym_type,
            "file":       file_path,
            "start_line": start_line,
            "end_line":   end_line,
            "code":       source_snippet or signature,
            "content":    source_snippet or signature,
            "docstring":  "",
            "imports":    [],
            "score":      score,
            "_source":    "graph",   # diagnostic tag — indicates graph route was used
        }

    def _read_source_span(self, file_path: str, start_line: int, end_line: int) -> str:
        """
        Read source lines [start_line, end_line] from disk.
        Returns empty string on any error (graceful degradation).
        Resolves relative paths against cwd.
        """
        try:
            abs_path = file_path if os.path.isabs(file_path) else os.path.join(os.getcwd(), file_path)
            if not os.path.exists(abs_path):
                return ""
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            # Line numbers are 1-indexed
            s = max(0, start_line - 1)
            e = min(len(lines), end_line)
            return "".join(lines[s:e])
        except Exception:
            return ""
