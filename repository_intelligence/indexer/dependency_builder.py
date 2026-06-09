from dataclasses import dataclass

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import (
    Symbol,
    SymbolRelationship
)


@dataclass
class SymbolGraphEdge:

    source: str | None
    target: str | None
    target_name: str | None
    relationship_type: str
    confidence: float


class SymbolRelationshipGraphBuilder:

    def build(
        self,
        repository_id,
        relationship_types: set[str] | None = None
    ) -> list[SymbolGraphEdge]:

        session = SessionLocal()

        try:
            source = Symbol
            target = Symbol.__table__.alias("target_symbol")
            query = (
                session.query(
                    source.qualified_name.label("source_name"),
                    target.c.qualified_name.label("target_qualified_name"),
                    SymbolRelationship.target_name,
                    SymbolRelationship.relationship_type,
                    SymbolRelationship.confidence
                )
                .select_from(SymbolRelationship)
                .outerjoin(
                    source,
                    SymbolRelationship.source_symbol_id == source.id
                )
                .outerjoin(
                    target,
                    SymbolRelationship.target_symbol_id == target.c.id
                )
                .filter(
                    SymbolRelationship.repository_id == repository_id
                )
            )

            if relationship_types:
                query = query.filter(
                    SymbolRelationship.relationship_type.in_(
                        relationship_types
                    )
                )

            return [
                SymbolGraphEdge(
                    source=row.source_name,
                    target=row.target_qualified_name,
                    target_name=row.target_name,
                    relationship_type=row.relationship_type,
                    confidence=float(row.confidence)
                )
                for row in query.all()
            ]

        finally:
            session.close()
