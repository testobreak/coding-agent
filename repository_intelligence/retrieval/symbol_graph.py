# repository_intelligence/retrieval/symbol_graph.py
"""
Symbol Graph utilities for Local Cursor.
Provides fast graph‑based look‑ups and relationship queries using the
SQLAlchemy ORM models defined in repository_intelligence.models.
"""

from __future__ import annotations

from collections import deque
from typing import List, Tuple

from sqlalchemy.orm import Session

from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.file import File


class SymbolGraph:
    """Utility class to query the symbol relationship graph.

    The graph is represented by the ``symbol_relationships`` table where each
    row links a *source* symbol (or file) to a *target* symbol name. This class
    provides a lightweight BFS to discover related symbols up to a configurable
    depth.
    """

    def __init__(self, session: Session):
        self.session = session

    def _direct_targets(self, source_symbol_id: str) -> List[Tuple[str, str]]:
        """Return a list of ``(target_name, relationship_type)`` for a given
        source symbol identifier.
        """
        rows = (
            self.session.query(SymbolRelationship.target_name, SymbolRelationship.relationship_type)
            .filter(SymbolRelationship.source_symbol_id == source_symbol_id)
            .all()
        )
        return [(r[0], r[1]) for r in rows]

    def bfs_related_symbols(self, start_symbol_id: str, max_depth: int = 2) -> List[Symbol]:
        """Breadth‑first search from *start_symbol_id* returning Symbol objects
        reachable within ``max_depth`` edges.
        """
        visited = set([start_symbol_id])
        queue = deque([(start_symbol_id, 0)])
        results: List[Symbol] = []

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for target_name, _ in self._direct_targets(current_id):
                target_symbol = (
                    self.session.query(Symbol)
                    .filter(Symbol.qualified_name == target_name)
                    .first()
                )
                if target_symbol and target_symbol.id not in visited:
                    visited.add(target_symbol.id)
                    results.append(target_symbol)
                    queue.append((target_symbol.id, depth + 1))
        return results

    def related_symbols_for_file(self, file_id: str, max_depth: int = 2) -> List[Symbol]:
        """Collect symbols referenced by a file (via ``USES`` relationships) and
        then expand the graph.
        """
        file_symbols = (
            self.session.query(Symbol)
            .filter(Symbol.file_id == file_id)
            .all()
        )
        all_related: List[Symbol] = []
        for sym in file_symbols:
            all_related.extend(self.bfs_related_symbols(sym.id, max_depth))
        return all_related

    def candidate_symbols(self, query: str, limit: int = 100) -> List[Symbol]:
        """Simple lexical candidate lookup – symbols whose name or qualified name
        contains the query string (case‑insensitive).
        """
        pattern = f"%{query}%"
        return (
            self.session.query(Symbol)
            .filter(
                Symbol.name.ilike(pattern) | Symbol.qualified_name.ilike(pattern)
            )
            .limit(limit)
            .all()
        )

# End of file
