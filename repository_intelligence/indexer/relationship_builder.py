from repository_intelligence.indexer.symbol_extractor import (
    ExtractedRelationship,
    ExtractedTest
)
from repository_intelligence.models.file import File
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.symbol import (
    Symbol,
    SymbolRelationship,
    Test
)
from repository_intelligence.services.symbol_resolver import SymbolResolver


class RelationshipBuilder:

    def __init__(self):
        self.resolver = SymbolResolver()

    def persist(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_relationships: list[ExtractedRelationship],
        extracted_tests: list[ExtractedTest],
        symbols_by_name: dict[str, Symbol]
    ) -> None:

        self.persist_relationships(
            session,
            repository,
            file_row,
            extracted_relationships,
            symbols_by_name
        )
        self.persist_tests(
            session,
            repository,
            file_row,
            extracted_tests,
            symbols_by_name
        )

    def persist_relationships(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_relationships: list[ExtractedRelationship],
        symbols_by_name: dict[str, Symbol]
    ) -> None:

        for relationship in extracted_relationships:
            source = symbols_by_name.get(
                relationship.source_qualified_name
            )
            target = self.resolve_symbol(
                session,
                repository,
                relationship.target_name,
                file_row
            )

            session.add(
                SymbolRelationship(
                    repository_id=repository.id,
                    source_symbol_id=source.id if source else None,
                    target_symbol_id=target.id if target else None,
                    source_file_id=file_row.id,
                    target_name=relationship.target_name,
                    relationship_type=relationship.relationship_type,
                    confidence=relationship.confidence,
                    metadata_=relationship.metadata
                )
            )

    def persist_tests(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_tests: list[ExtractedTest],
        symbols_by_name: dict[str, Symbol]
    ) -> None:

        for test in extracted_tests:
            symbol = symbols_by_name.get(
                test.symbol_qualified_name
            )
            target = (
                self.resolve_symbol(
                    session,
                    repository,
                    test.target_name,
                    file_row
                )
                if test.target_name
                else None
            )
            session.add(
                Test(
                    repository_id=repository.id,
                    file_id=file_row.id,
                    symbol_id=symbol.id if symbol else None,
                    name=test.name,
                    framework=test.framework,
                    target_symbol_id=target.id if target else None,
                    metadata_=test.metadata
                )
            )

            if symbol:
                session.add(
                    SymbolRelationship(
                        repository_id=repository.id,
                        source_symbol_id=symbol.id,
                        target_symbol_id=target.id if target else None,
                        source_file_id=file_row.id,
                        target_name=test.target_name,
                        relationship_type="TESTS",
                        confidence=0.75 if target else 0.4,
                        metadata_={
                            **test.metadata,
                            "framework": test.framework
                        }
                    )
                )

    def resolve_symbol(
        self,
        session,
        repository: Repository,
        target_name: str | None,
        source_file: File | None = None
    ) -> Symbol | None:

        resolved = self.resolver.resolve(
            session,
            repository.id,
            target_name,
            source_file
        )
        if isinstance(resolved, list):
            return resolved[0] if resolved else None
        return resolved

    def resolve_pending_targets(
        self,
        session,
        repository: Repository
    ) -> int:

        relationships = (
            session.query(SymbolRelationship)
            .filter(
                SymbolRelationship.repository_id == repository.id,
                SymbolRelationship.target_symbol_id.is_(None),
                SymbolRelationship.target_name.isnot(None)
            )
            .all()
        )
        resolved = 0

        for relationship in relationships:
            source_file = None
            if relationship.source_file_id:
                source_file = (
                    session.query(File)
                    .filter(File.id == relationship.source_file_id)
                    .first()
                )

            target = self.resolve_symbol(
                session,
                repository,
                relationship.target_name,
                source_file
            )

            if not target:
                continue

            relationship.target_symbol_id = target.id
            resolved += 1

        return resolved
