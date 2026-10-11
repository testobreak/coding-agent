# repository_intelligence/retrieval/graph_traversal.py
"""
Graph Traversal API for Local Cursor.

Provides cursor-style navigation APIs:
  - find_callers(symbol_id)      → who calls this symbol?
  - find_callees(symbol_id)      → what does this symbol call?
  - find_implementors(iface_id)  → who implements this interface?
  - impact_analysis(symbol_id)   → full neighbourhood for impact reporting
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.symbol import Test


class GraphTraversal:
    """Cursor-style graph traversal over the symbol_relationships table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # find_callers — reverse CALLS edges
    # ------------------------------------------------------------------

    def find_callers(self, symbol_id: str) -> List[Symbol]:
        """Return all symbols that call *symbol_id* (reverse CALLS edges)."""
        rows = (
            self.session.query(SymbolRelationship)
            .filter(
                SymbolRelationship.target_symbol_id == symbol_id,
                SymbolRelationship.relationship_type == "CALLS",
            )
            .all()
        )
        results: List[Symbol] = []
        seen = set()
        for rel in rows:
            if rel.source_symbol_id and rel.source_symbol_id not in seen:
                sym = (
                    self.session.query(Symbol)
                    .filter(Symbol.id == rel.source_symbol_id)
                    .first()
                )
                if sym:
                    results.append(sym)
                    seen.add(sym.id)
        return results

    # ------------------------------------------------------------------
    # find_callees — forward CALLS edges
    # ------------------------------------------------------------------

    def find_callees(self, symbol_id: str) -> List[Symbol]:
        """Return all symbols that *symbol_id* calls (forward CALLS edges)."""
        rows = (
            self.session.query(SymbolRelationship)
            .filter(
                SymbolRelationship.source_symbol_id == symbol_id,
                SymbolRelationship.relationship_type == "CALLS",
            )
            .all()
        )
        results: List[Symbol] = []
        seen = set()
        for rel in rows:
            if rel.target_symbol_id and rel.target_symbol_id not in seen:
                sym = (
                    self.session.query(Symbol)
                    .filter(Symbol.id == rel.target_symbol_id)
                    .first()
                )
                if sym:
                    results.append(sym)
                    seen.add(sym.id)
        return results

    # ------------------------------------------------------------------
    # find_implementors — IMPLEMENTS edges
    # ------------------------------------------------------------------

    def find_implementors(self, interface_id: str) -> List[Symbol]:
        """Return all classes that implement the given interface.

        Matches against both resolved ``target_symbol_id`` and unresolved
        ``target_name`` fallback (using the interface's short name).
        """
        # Try to get the interface symbol to access its short name
        iface_sym = (
            self.session.query(Symbol)
            .filter(Symbol.id == interface_id)
            .first()
        )
        iface_name = iface_sym.name if iface_sym else None

        q = self.session.query(SymbolRelationship).filter(
            SymbolRelationship.relationship_type == "IMPLEMENTS",
        )
        if iface_sym:
            q = q.filter(
                (SymbolRelationship.target_symbol_id == interface_id)
                | (SymbolRelationship.target_name == iface_name)
                | (SymbolRelationship.target_name == (iface_sym.qualified_name or iface_name))
            )
        else:
            return []

        rows = q.all()
        results: List[Symbol] = []
        seen = set()
        for rel in rows:
            if rel.source_symbol_id and rel.source_symbol_id not in seen:
                sym = (
                    self.session.query(Symbol)
                    .filter(Symbol.id == rel.source_symbol_id)
                    .first()
                )
                if sym:
                    results.append(sym)
                    seen.add(sym.id)
        return results

    # ------------------------------------------------------------------
    # find_subclasses — EXTENDS edges
    # ------------------------------------------------------------------

    def find_subclasses(self, class_id: str) -> List[Symbol]:
        """Return all direct subclasses of the given class."""
        sym = self.session.query(Symbol).filter(Symbol.id == class_id).first()
        if not sym:
            return []
        rows = (
            self.session.query(SymbolRelationship)
            .filter(
                SymbolRelationship.relationship_type == "EXTENDS",
                (
                    (SymbolRelationship.target_symbol_id == class_id)
                    | (SymbolRelationship.target_name == sym.name)
                    | (SymbolRelationship.target_name == sym.qualified_name)
                ),
            )
            .all()
        )
        results: List[Symbol] = []
        seen = set()
        for rel in rows:
            if rel.source_symbol_id and rel.source_symbol_id not in seen:
                child = (
                    self.session.query(Symbol)
                    .filter(Symbol.id == rel.source_symbol_id)
                    .first()
                )
                if child:
                    results.append(child)
                    seen.add(child.id)
        return results

    # ------------------------------------------------------------------
    # find_tests — TESTS edges
    # ------------------------------------------------------------------

    def find_tests(self, symbol_id: str) -> List[Symbol]:
        """Return all test symbols that target *symbol_id*."""
        rows = (
            self.session.query(SymbolRelationship)
            .filter(
                SymbolRelationship.target_symbol_id == symbol_id,
                SymbolRelationship.relationship_type == "TESTS",
            )
            .all()
        )
        results: List[Symbol] = []
        seen = set()
        for rel in rows:
            if rel.source_symbol_id and rel.source_symbol_id not in seen:
                sym = (
                    self.session.query(Symbol)
                    .filter(Symbol.id == rel.source_symbol_id)
                    .first()
                )
                if sym:
                    results.append(sym)
                    seen.add(sym.id)
        return results

    # ------------------------------------------------------------------
    # impact_analysis — full neighbourhood
    # ------------------------------------------------------------------

    def impact_analysis(self, symbol_id: str) -> Dict:
        """Collect the full neighbourhood of a symbol for impact reporting.

        Returns a dict::

            {
                "symbol": Symbol,
                "callers": [Symbol, ...],
                "callees": [Symbol, ...],
                "implementors": [Symbol, ...],
                "subclasses": [Symbol, ...],
                "tests": [Symbol, ...],
            }

        Useful for answering: *"what breaks if I change this?"*
        """
        symbol = (
            self.session.query(Symbol).filter(Symbol.id == symbol_id).first()
        )
        return {
            "symbol": symbol,
            "callers": self.find_callers(symbol_id),
            "callees": self.find_callees(symbol_id),
            "implementors": self.find_implementors(symbol_id),
            "subclasses": self.find_subclasses(symbol_id),
            "tests": self.find_tests(symbol_id),
        }

    # ------------------------------------------------------------------
    # expand — collect neighbour symbols for a list of seed symbols
    # ------------------------------------------------------------------

    def expand(self, symbols: List[Symbol], depth: int = 1) -> List[Symbol]:
        """Expand a seed list of symbols by graph neighbourhood.

        Used by the candidate pipeline to augment semantic results with
        graph-adjacent symbols.
        """
        seen_ids = {s.id for s in symbols}
        result: List[Symbol] = list(symbols)

        for sym in symbols:
            neighbours = (
                self.find_callers(sym.id)
                + self.find_callees(sym.id)
                + self.find_implementors(sym.id)
                + self.find_subclasses(sym.id)
            )
            for n in neighbours:
                if n.id not in seen_ids:
                    seen_ids.add(n.id)
                    result.append(n)

        return result
