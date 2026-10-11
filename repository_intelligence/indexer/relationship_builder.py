import re
from pathlib import Path
from typing import Optional

from repository_intelligence.indexer.symbol_extractor import (
    ExtractedRelationship,
    ExtractedSymbol,
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
        self._call_graph_builder = None  # lazy import to keep startup fast
        self._type_resolver = None       # lazy import

    def persist(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_relationships: list[ExtractedRelationship],
        extracted_tests: list[ExtractedTest],
        symbols_by_name: dict[str, Symbol],
        file_path: Optional[str] = None,
        file_language: Optional[str] = None,
        extracted_symbols: Optional[list] = None,
    ) -> None:
        """Persist all relationship types for a single indexed file."""

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

        # ---- Phase 5 additional passes ----
        if extracted_symbols:
            self._build_return_edges(
                session, repository, file_row, extracted_symbols, symbols_by_name
            )
            self._build_field_ref_edges(
                session, repository, file_row, extracted_symbols, symbols_by_name
            )

        if file_path and file_language == "java":
            self._build_call_graph_edges(
                session, repository, file_row, symbols_by_name,
                file_path=file_path
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

    # ------------------------------------------------------------------
    # Phase 5 — additional edge builders
    # ------------------------------------------------------------------

    def _build_return_edges(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_symbols: list,
        symbols_by_name: dict[str, Symbol],
    ) -> None:
        """Add METHOD -> RETURNS -> TypeSymbol edges."""
        for sym in extracted_symbols:
            if sym.symbol_type not in ("METHOD", "FUNCTION"):
                continue
            sig = sym.signature or ""
            # Extract return type from signature: e.g. "public Employee createEmployee(...)"
            # Simple heuristic: first word that is CamelCase and not a modifier
            modifiers = {"public", "private", "protected", "static", "final",
                         "abstract", "synchronized", "native", "strictfp", "void"}
            tokens = sig.split()
            return_type = None
            for tok in tokens:
                clean = re.sub(r"<.*", "", tok).strip("(){};")
                if clean and clean not in modifiers and clean[0].isupper():
                    return_type = clean
                    break

            if not return_type:
                continue

            source_sym = symbols_by_name.get(sym.qualified_name)
            if not source_sym:
                continue

            target = self.resolve_symbol(session, repository, return_type, file_row)
            session.add(SymbolRelationship(
                repository_id=repository.id,
                source_symbol_id=source_sym.id,
                target_symbol_id=target.id if target else None,
                source_file_id=file_row.id,
                target_name=return_type,
                relationship_type="RETURNS",
                confidence=0.8,
                metadata_={"from": "return_edge_builder"},
            ))

    def _build_field_ref_edges(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_symbols: list,
        symbols_by_name: dict[str, Symbol],
    ) -> None:
        """Add METHOD -> REFERENCES -> FieldSymbol edges for injected fields."""
        # Collect all FIELD symbols in this file
        field_syms = [
            s for s in extracted_symbols if s.symbol_type == "FIELD"
        ]
        method_syms = [
            s for s in extracted_symbols
            if s.symbol_type in ("METHOD", "FUNCTION")
        ]
        for method_sym in method_syms:
            method_row = symbols_by_name.get(method_sym.qualified_name)
            if not method_row:
                continue
            for field_sym in field_syms:
                field_row = symbols_by_name.get(field_sym.qualified_name)
                if not field_row:
                    continue
                session.add(SymbolRelationship(
                    repository_id=repository.id,
                    source_symbol_id=method_row.id,
                    target_symbol_id=field_row.id,
                    source_file_id=file_row.id,
                    target_name=field_sym.name,
                    relationship_type="REFERENCES",
                    confidence=0.5,
                    metadata_={"from": "field_ref_builder"},
                ))

    def _build_call_graph_edges(
        self,
        session,
        repository: Repository,
        file_row: File,
        symbols_by_name: dict[str, Symbol],
        file_path: str,
    ) -> None:
        """Run CallGraphBuilder on a Java file and persist CALLS edges."""
        try:
            if self._call_graph_builder is None:
                from repository_intelligence.indexer.call_graph_builder import CallGraphBuilder
                self._call_graph_builder = CallGraphBuilder()

            if self._type_resolver is None:
                from repository_intelligence.parsers.java_type_resolver import TypeResolver
                self._type_resolver = TypeResolver()

            # Build symbol table for this file: varName -> TypeName
            symbol_table = self._type_resolver._get_symbol_table(file_path, None)

            # Derive file namespace from first symbol's qualified_name
            file_namespace = ""
            for sym in symbols_by_name.values():
                if sym.qualified_name and "." in sym.qualified_name:
                    file_namespace = ".".join(sym.qualified_name.split(".")[:-1])
                    break

            call_rels = self._call_graph_builder.extract(
                file_path=file_path,
                symbol_table=symbol_table,
                file_namespace=file_namespace,
            )

            for rel in call_rels:
                source_sym = symbols_by_name.get(rel.source_qualified_name)
                target_sym = self.resolve_symbol(
                    session, repository, rel.target_name, file_row
                )
                session.add(SymbolRelationship(
                    repository_id=repository.id,
                    source_symbol_id=source_sym.id if source_sym else None,
                    target_symbol_id=target_sym.id if target_sym else None,
                    source_file_id=file_row.id,
                    target_name=rel.target_name,
                    relationship_type="CALLS",
                    confidence=float(rel.confidence),
                    metadata_=rel.metadata,
                ))
        except Exception as exc:
            print(f"[RelationshipBuilder] Call-graph extraction failed for {file_path}: {exc}")
