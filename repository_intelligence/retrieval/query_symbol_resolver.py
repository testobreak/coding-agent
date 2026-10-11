# repository_intelligence/retrieval/query_symbol_resolver.py
"""
Query Symbol Resolver — the symbol-first retrieval entry-point for Local Cursor.

Pipeline:
    raw query (str)
     ├─ Step 1: lexical extraction   (CamelCase / camelCase regex)
     ├─ Step 2: symbol DB lookup     (exact → prefix → fuzzy)
     └─ Step 3: graph expansion      (implementors + callers + callees)

Returns a ranked list of Symbol objects ready to be used as retrieval context.
"""

from __future__ import annotations

import re
from typing import List, Optional

from sqlalchemy.orm import Session

from repository_intelligence.models.symbol import Symbol
from repository_intelligence.retrieval.graph_traversal import GraphTraversal


# ---------------------------------------------------------------------------
# Patterns for lexical extraction
# ---------------------------------------------------------------------------

# Matches: UpperCamelCase  e.g. EmployeeService, JpaRepository
_CAMEL_UPPER_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]+(?:[A-Z][a-zA-Z0-9]+)*\b")

# Matches: lowerCamelCase  e.g. employeeRepository, createEmployee
_CAMEL_LOWER_RE = re.compile(r"\b[a-z][a-z0-9]*(?:[A-Z][a-zA-Z0-9]+)+\b")

# Matches: package.name notation
_QUALIFIED_RE = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b")

# Common English stop-words that should not be treated as symbol hints
_STOP_WORDS = {
    "add", "create", "update", "delete", "remove", "get", "set", "fetch",
    "find", "search", "list", "show", "display", "print", "log", "fix",
    "implement", "use", "call", "change", "modify", "check", "test", "run",
    "build", "make", "write", "return", "throw", "catch", "handle", "register",
    "the", "a", "an", "of", "in", "to", "for", "on", "at", "by", "with",
    "from", "and", "or", "but", "all", "it", "this", "that", "method",
    "function", "class", "interface", "field", "variable", "service",
    "repository", "controller", "entity", "model", "dto", "response",
}


class QuerySymbolResolver:
    """Resolve a raw natural-language query into Symbol objects via symbol-first lookup.

    Args:
        session: SQLAlchemy session (caller owns lifecycle).
        repository_id: UUID of the repository to search in.
    """

    def __init__(self, session: Session, repository_id) -> None:
        self.session = session
        self.repository_id = repository_id
        self._traversal = GraphTraversal(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        query: str,
        active_file: Optional[str] = None,
        expand_graph: bool = True,
        max_results: int = 20,
    ) -> List[Symbol]:
        """Resolve *query* into a ranked list of Symbol objects.

        Args:
            query:        Raw natural-language query string.
            active_file:  Currently open file path (adds proximity boost).
            expand_graph: If True, expand results via graph neighbourhood.
            max_results:  Cap on total returned symbols.
        """
        # Step 1 — extract candidate symbol names from query
        hints = self._extract_symbol_hints(query)
        if not hints:
            return []

        # Step 2 — DB lookup for each hint
        found: dict[str, Symbol] = {}
        for hint in hints:
            for sym in self._lookup(hint):
                found[sym.id] = sym

        if not found:
            return []

        seed = list(found.values())

        # Step 3 — graph expansion
        if expand_graph:
            expanded = self._traversal.expand(seed, depth=1)
        else:
            expanded = seed

        # Deduplicate keeping order
        seen_ids: set = set()
        unique: List[Symbol] = []
        for s in expanded:
            if s.id not in seen_ids:
                seen_ids.add(s.id)
                unique.append(s)

        return unique[:max_results]

    # ------------------------------------------------------------------
    # Step 1 — lexical extraction
    # ------------------------------------------------------------------

    def _extract_symbol_hints(self, query: str) -> List[str]:
        """Extract candidate symbol names from a free-text query."""
        hints: List[str] = []

        # UpperCamelCase — most reliable signal
        for m in _CAMEL_UPPER_RE.finditer(query):
            word = m.group()
            if word.lower() not in _STOP_WORDS:
                hints.append(word)

        # lowerCamelCase — method / field names
        for m in _CAMEL_LOWER_RE.finditer(query):
            word = m.group()
            if word.lower() not in _STOP_WORDS:
                hints.append(word)

        # Qualified names e.g. com.example.service
        for m in _QUALIFIED_RE.finditer(query):
            hints.append(m.group())

        # Deduplicate while preserving order
        seen: set = set()
        unique: List[str] = []
        for h in hints:
            if h not in seen:
                seen.add(h)
                unique.append(h)

        return unique

    # ------------------------------------------------------------------
    # Step 2 — DB lookup (exact → prefix → fuzzy)
    # ------------------------------------------------------------------

    def _lookup(self, hint: str) -> List[Symbol]:
        """Multi-stage DB lookup for a single symbol name hint."""
        results: dict[str, Symbol] = {}

        # a) Exact qualified name
        exact = (
            self.session.query(Symbol)
            .filter(
                Symbol.repository_id == self.repository_id,
                Symbol.qualified_name == hint,
            )
            .all()
        )
        for s in exact:
            results[s.id] = s

        # b) Exact short name
        by_name = (
            self.session.query(Symbol)
            .filter(
                Symbol.repository_id == self.repository_id,
                Symbol.name == hint,
            )
            .limit(10)
            .all()
        )
        for s in by_name:
            results[s.id] = s

        # c) Qualified name ends-with hint (suffix match)
        suffix = (
            self.session.query(Symbol)
            .filter(
                Symbol.repository_id == self.repository_id,
                Symbol.qualified_name.endswith(f".{hint}"),
            )
            .limit(10)
            .all()
        )
        for s in suffix:
            results[s.id] = s

        # d) Fuzzy prefix on short name (only if still empty)
        if not results:
            prefix = (
                self.session.query(Symbol)
                .filter(
                    Symbol.repository_id == self.repository_id,
                    Symbol.name.startswith(hint),
                )
                .limit(10)
                .all()
            )
            for s in prefix:
                results[s.id] = s

        return list(results.values())
