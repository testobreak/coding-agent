# retrieval/query_resolver.py
#
# Query Resolution Layer — the brain of Local Cursor's retrieval pipeline.
#
# Architecture:
#   Every developer query passes through this resolver BEFORE any retrieval.
#   The resolver decides which execution substrate to use:
#
#     SYMBOL  → SymbolGraphCache in-memory lookup (~0 ms)  — no ANN
#     GRAPH   → Graph traversal via SymbolGraphCache (~1-5 ms) — no ANN
#     SEMANTIC → ANN + BM25 + CandidatePipeline fallback (~50-200 ms)
#
# Rule: Never run ANN retrieval until structural resolution fails.

import re
from dataclasses import dataclass, field
from typing import List, Optional

from retrieval.query_intent import ResolutionMode, GRAPH_OP_PATTERNS


# ── ResolutionPlan ────────────────────────────────────────────────────────────

@dataclass
class ResolutionPlan:
    """
    The output of QueryResolver.resolve().

    mode       — which execution route to use (SYMBOL / GRAPH / SEMANTIC)
    symbols    — list of resolved in-memory graph symbol dicts (may be empty for SEMANTIC)
    graph_op   — graph operation name if mode=GRAPH ("callers", "deps", "impls", etc.)
    query      — original query string (passed through to semantic fallback)
    symbol_names — raw CamelCase tokens extracted from query (diagnostic)
    """
    mode:         ResolutionMode
    symbols:      List[dict]   = field(default_factory=list)
    graph_op:     Optional[str] = None
    query:        str           = ""
    symbol_names: List[str]    = field(default_factory=list)


# ── Token extraction helpers ─────────────────────────────────────────────────

# Blacklisted tokens that look like symbols but are English action words
_VERB_BLACKLIST = frozenset({
    "add", "fix", "update", "remove", "change", "modify", "delete",
    "implement", "create", "test", "explain", "get", "set", "run",
    "show", "find", "list", "check", "rename", "refactor", "log",
    "print", "return", "call", "use", "make", "build", "load",
    "save", "send", "read", "write", "parse", "handle", "process",
})

def _extract_symbol_tokens(query: str) -> List[str]:
    """
    Pull candidate symbol names from a natural-language query.

    Strategies:
      1. CamelCase words: EmployeeService, updateSalary
      2. Adjacent CamelCase sequences joined: "Employee Service" → EmployeeService
      3. Dotted qualified names: com.example.Service
    """
    tokens: List[str] = []

    # 1. CamelCase identifiers
    camel = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', query)
    tokens.extend(camel)

    # 2. Dotted qualified names
    dotted = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+\b', query)
    tokens.extend(dotted)

    # 3. Adjacent CamelCase words combined ("Employee Service" → "EmployeeService")
    seq_matches = re.findall(r'\b(?:[A-Z][a-zA-Z0-9_]*\s+)+[A-Z][a-zA-Z0-9_]*\b', query)
    for seq in seq_matches:
        combined = "".join(seq.split())
        tokens.append(combined)

    # 4. lowerCamelCase method names (e.g., updateSalary, createEmployee)
    lower_camel = re.findall(r'\b[a-z][a-zA-Z0-9_]*[A-Z][a-zA-Z0-9_]*\b', query)
    tokens.extend(lower_camel)

    # Deduplicate and filter blacklisted verbs
    seen = set()
    result = []
    for tok in tokens:
        norm = tok.lower()
        if norm in _VERB_BLACKLIST:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        result.append(tok)

    return result


# ── Graph operation detection ────────────────────────────────────────────────

def _detect_graph_op(query: str) -> Optional[str]:
    """
    Check whether the query is asking a structural/relational question.
    Returns the graph operation name or None.

    Uses GRAPH_OP_PATTERNS from query_intent.py.
    """
    q_lower = query.lower()
    for patterns, op_name in GRAPH_OP_PATTERNS:
        for pattern in patterns:
            # Use regex to support wildcard patterns (e.g. "what does .* call")
            try:
                if re.search(pattern, q_lower):
                    return op_name
            except re.error:
                # Literal fallback
                if pattern in q_lower:
                    return op_name
    return None


# ── QueryResolver ─────────────────────────────────────────────────────────────

class QueryResolver:
    """
    Three-stage structural query resolver.

    Stage 1 — Symbol lookup (in-memory, ~0 ms)
        Extract CamelCase / lowerCamelCase token candidates.
        Look them up in SymbolGraphCache.
        If any resolve → mode=SYMBOL (no ANN needed).

    Stage 2 — Graph intent detection (~0 ms)
        Check query for structural keywords ("callers of", "deps of", etc.).
        If matched AND a symbol was found → mode=GRAPH.
        If matched but no symbol → still try GRAPH with best-effort name match.

    Stage 3 — Semantic fallback
        If neither symbol nor graph pattern matched → mode=SEMANTIC.
        This triggers ANN + BM25 + CandidatePipeline.
    """

    def resolve(self, query: str, repo_root: str = ".") -> ResolutionPlan:
        """
        Resolve a developer query to a ResolutionPlan.

        Args:
            query:     Natural-language developer query.
            repo_root: Repository root path (unused in graph-cache path).

        Returns:
            ResolutionPlan with mode, resolved symbols, and graph_op.
        """
        # ── Step 1: Extract candidate symbol tokens ────────────────────────
        symbol_tokens = _extract_symbol_tokens(query)

        # ── Step 2: Detect graph-structural intent ─────────────────────────
        graph_op = _detect_graph_op(query)

        # ── Step 3: Attempt symbol resolution from in-memory graph cache ───
        resolved_symbols = []
        if symbol_tokens:
            resolved_symbols = self._lookup_symbols(symbol_tokens, repo_root=repo_root)

        # ── Step 4: Route ───────────────────────────────────────────────────
        #
        # Priority order:
        #   GRAPH   — query has structural keywords AND at least one symbol resolved
        #   SYMBOL  — at least one symbol resolved (no structural keyword)
        #   GRAPH   — structural keywords but no symbol resolved (best-effort)
        #   SEMANTIC — nothing resolved

        if graph_op and resolved_symbols:
            # Best case: structural question + known symbol → pure graph traversal
            return ResolutionPlan(
                mode=ResolutionMode.GRAPH,
                symbols=resolved_symbols,
                graph_op=graph_op,
                query=query,
                symbol_names=symbol_tokens,
            )

        if resolved_symbols and not graph_op:
            # Known symbol, no structural pattern → direct symbol route
            return ResolutionPlan(
                mode=ResolutionMode.SYMBOL,
                symbols=resolved_symbols,
                graph_op=None,
                query=query,
                symbol_names=symbol_tokens,
            )

        if graph_op and not resolved_symbols:
            # Structural question but symbol not in graph (may be partially indexed).
            # Return GRAPH mode with empty symbols — GraphResolver will do best-effort.
            return ResolutionPlan(
                mode=ResolutionMode.GRAPH,
                symbols=[],
                graph_op=graph_op,
                query=query,
                symbol_names=symbol_tokens,
            )

        # Fallback: fuzzy/conceptual query → ANN
        return ResolutionPlan(
            mode=ResolutionMode.SEMANTIC,
            symbols=[],
            graph_op=None,
            query=query,
            symbol_names=symbol_tokens,
        )

    def _lookup_symbols(self, tokens: List[str], repo_root: str = ".") -> List[dict]:
        """
        Lookup tokens against the in-memory SymbolGraphCache.
        Returns list of matching symbol dicts (may be empty).
        Tolerant of cache not loaded — falls back gracefully to SEMANTIC.

        Snapshot-aware: if the cache was loaded against a different repo
        snapshot than the current one, returns empty (forces SEMANTIC cascade)
        to prevent stale symbol IDs from being used.
        """
        try:
            from retrieval.symbol_graph_cache import SymbolGraphCache
            cache = SymbolGraphCache.get_instance()

            # Warm the cache if not yet loaded (lazy warm on first resolve call)
            if not cache.is_loaded:
                cache.load(repo_root=repo_root)

            if not cache.is_loaded:
                # DB unavailable — skip structural routing entirely
                return []

            # Snapshot staleness guard — if the graph was loaded against a
            # different repo snapshot than the current one, serving its symbol IDs would be incorrect.
            try:
                from repository.snapshot_manager import SnapshotManager
                current_snap = SnapshotManager().current_snapshot(repo_root)
                if cache.is_stale(current_snap.snapshot_id):
                    print(
                        f"[QueryResolver] Graph cache stale "
                        f"(cache={cache.snapshot_id[:8]}, "
                        f"current={current_snap.snapshot_id[:8]}) "
                        f"— cascading to SEMANTIC"
                    )
                    return []
            except Exception:
                pass  # snapshot check failed — optimistically proceed

            results = []
            seen_ids = set()

            for token in tokens:
                # Exact name match (case-insensitive)
                matches = cache.get_symbols_by_name(token)
                for sym in matches:
                    sym_id = sym.get("id")
                    if sym_id and sym_id not in seen_ids:
                        seen_ids.add(sym_id)
                        results.append(sym)

                # Qualified name match
                qn_match = cache.get_symbol_by_qualified_name(token)
                if qn_match:
                    sym_id = qn_match.get("id")
                    if sym_id and sym_id not in seen_ids:
                        seen_ids.add(sym_id)
                        results.append(qn_match)

            return results

        except Exception as e:
            # Graph cache unavailable — degrade gracefully to SEMANTIC
            print(f"[QueryResolver] Symbol lookup failed (degrading to SEMANTIC): {e}")
            return []
