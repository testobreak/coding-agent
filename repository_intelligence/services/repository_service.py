from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func

from repository_intelligence.db.connection import Base, SessionLocal, engine
from repository_intelligence.indexer.embedding_builder import (
    EmbeddingBuilder
)
from repository_intelligence.indexer.file_indexer import (
    FileIndexer
)
from repository_intelligence.indexer.relationship_builder import (
    RelationshipBuilder
)
from repository_intelligence.indexer.repository_scanner import (
    RepositoryScanner
)
from repository_intelligence.indexer.symbol_extractor import (
    SymbolExtractor
)
from repository_intelligence.models.file import File
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.symbol import (
    Embedding,
    IndexJob,
    RepairPattern,
    Symbol,
    SymbolRelationship,
    Test
)


class RepositoryService:

    def __init__(self):

        self.scanner = (
            RepositoryScanner()
        )
        self.extractor = (
            SymbolExtractor()
        )
        self.file_indexer = (
            FileIndexer()
        )
        self.relationship_builder = (
            RelationshipBuilder()
        )
        self.embedding_builder = (
            EmbeddingBuilder()
        )
        Base.metadata.create_all(bind=engine)

    def scan_repository(
        self,
        repository_root: str
    ):

        repository_root_path = Path(repository_root).resolve()
        session = SessionLocal()

        repository = self._get_or_create_repository(
            session,
            repository_root_path
        )
        session.commit()

        job = IndexJob(
            repository_id=repository.id,
            status="RUNNING",
            reason="incremental_scan"
        )
        session.add(job)
        session.flush()

        try:
            known_hashes = self.file_indexer.known_hashes(
                session,
                repository
            )
            scan_result = self.scanner.scan_changes(
                str(repository_root_path),
                known_hashes
            )
            job.scanned_files = len(scan_result["scanned"])

            for file_info in scan_result["unchanged"]:
                self.file_indexer.upsert(
                    session,
                    repository,
                    file_info
                )

            for file_info in scan_result["changed"]:
                file_row = self.file_indexer.upsert(
                    session,
                    repository,
                    file_info
                )

                job.changed_files += 1
                self._index_changed_file(
                    session,
                    repository,
                    file_row,
                    file_info,
                    job
                )

            removed = self.file_indexer.delete_removed(
                session,
                repository,
                scan_result["removed"]
            )
            resolved_relationships = (
                self.relationship_builder.resolve_pending_targets(
                    session,
                    repository
                )
            )
            repair_patterns_created = (
                self._ensure_baseline_repair_patterns(
                    session,
                    repository
                )
            )

            job.status = "COMPLETED"
            job.completed_at = datetime.now(timezone.utc)
            job.metadata_ = {
                "removed_files": removed,
                "incremental": bool(known_hashes),
                "resolved_relationships": resolved_relationships,
                "repair_patterns_created": repair_patterns_created
            }

            session.commit()

            return {
                "repository_id": str(repository.id),
                "job_id": str(job.id),
                "scanned_files": job.scanned_files,
                "changed_files": job.changed_files,
                "changed_symbols": job.changed_symbols,
                "removed_files": removed,
                "incremental": bool(known_hashes),
                "resolved_relationships": resolved_relationships,
                "repair_patterns_created": repair_patterns_created
            }

        except Exception as exc:
            session.rollback()
            job.status = "FAILED"
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()
            raise

        finally:
            session.close()

    def index_repository_files(
        self,
        repository_root: str
    ) -> dict:

        repository_root_path = Path(repository_root).resolve()
        session = SessionLocal()

        try:
            repository = self._get_or_create_repository(
                session,
                repository_root_path
            )
            scanned_files = list(
                self.scanner.scan(
                    str(repository_root_path)
                )
            )
            result = self.file_indexer.sync(
                session,
                repository,
                scanned_files
            )
            session.commit()

            return {
                "repository_id": str(repository.id),
                "repository_root": str(repository_root_path),
                **result
            }

        except Exception:
            session.rollback()
            raise

        finally:
            session.close()

    def _get_or_create_repository(
        self,
        session,
        repository_root: Path
    ) -> Repository:

        root_path = str(repository_root)
        repository = (
            session.query(Repository)
            .filter(Repository.root_path == root_path)
            .one_or_none()
        )

        if repository:
            repository.updated_at = func.now()
            return repository

        repository = Repository(
            name=repository_root.name,
            root_path=root_path
        )
        session.add(repository)
        session.flush()

        return repository

    def _upsert_file(
        self,
        session,
        repository: Repository,
        file_info: dict
    ) -> File:

        file_row = (
            session.query(File)
            .filter(
                File.repository_id == repository.id,
                File.path == file_info["path"]
            )
            .one_or_none()
        )

        if file_row:
            return file_row

        file_row = File(
            repository_id=repository.id,
            path=file_info["path"],
            language=file_info["language"],
            file_hash="",
            size_bytes=file_info["size_bytes"]
        )
        session.add(file_row)
        session.flush()

        return file_row

    def _index_changed_file(
        self,
        session,
        repository: Repository,
        file_row: File,
        file_info: dict,
        job: IndexJob
    ) -> None:

        extraction = self.extractor.extract(
            file_info["absolute_path"],
            file_info["path"],
            file_info["language"]
        )
        source_text = Path(file_info["absolute_path"]).read_text(
            encoding="utf-8",
            errors="ignore"
        )

        self._clear_file_index(
            session,
            file_row
        )

        file_row.language = file_info["language"]
        file_row.file_hash = file_info["file_hash"]
        file_row.size_bytes = file_info["size_bytes"]
        file_row.updated_at = func.now()
        session.flush()
        self._create_file_embedding(
            session,
            repository,
            file_row,
            source_text
        )

        symbols_by_name = self._persist_symbols(
            session,
            repository,
            file_row,
            extraction.symbols
        )
        job.changed_symbols += len(symbols_by_name)

        self.relationship_builder.persist(
            session,
            repository,
            file_row,
            extraction.relationships,
            extraction.tests,
            symbols_by_name
        )

    def _persist_symbols(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_symbols: list
    ) -> dict[str, Symbol]:

        symbols_by_name = {}
        seen = set()
        unique_extracted_symbols = []

        # Deduplicate incoming symbols relative to unique key definitions
        for extracted in extracted_symbols:
            key = (extracted.qualified_name, extracted.symbol_type)
            if key in seen:
                continue
            seen.add(key)
            unique_extracted_symbols.append(extracted)

        # Persist unique symbol configurations
        for extracted in unique_extracted_symbols:
            symbol = Symbol(
                repository_id=repository.id,
                file_id=file_row.id,
                name=extracted.name,
                qualified_name=extracted.qualified_name,
                symbol_type=extracted.symbol_type,
                start_line=extracted.start_line,
                end_line=extracted.end_line,
                signature=extracted.signature,
                metadata_=extracted.metadata,
                source_hash=extracted.source_hash
            )
            session.add(symbol)
            session.flush()
            symbols_by_name[extracted.qualified_name] = symbol

        # Map hierarchical parent references consistently 
        for extracted in unique_extracted_symbols:
            if not extracted.parent_qualified_name:
                continue

            symbol = symbols_by_name.get(extracted.qualified_name)
            parent = symbols_by_name.get(extracted.parent_qualified_name)

            if symbol and parent:
                symbol.parent_symbol_id = parent.id

        # Populate vectorized embeddings data points
        for symbol in symbols_by_name.values():
            self._create_symbol_embedding(
                session,
                repository,
                symbol
            )

        return symbols_by_name

    def _persist_symbol_relationships(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_relationships: list,
        symbols_by_name: dict[str, Symbol]
    ) -> None:

        for relationship in extracted_relationships:
            source = symbols_by_name.get(
                relationship.source_qualified_name
            )
            target = self._resolve_symbol(
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

    def _persist_tests(
        self,
        session,
        repository: Repository,
        file_row: File,
        extracted_tests: list,
        symbols_by_name: dict[str, Symbol]
    ) -> None:

        for test in extracted_tests:
            symbol = symbols_by_name.get(
                test.symbol_qualified_name
            )
            target = (
                self._resolve_symbol(
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

    def _clear_file_index(
        self,
        session,
        file_row: File
    ) -> None:

        symbol_ids = [
            row.id for row in
            session.query(Symbol.id)
            .filter(Symbol.file_id == file_row.id)
            .all()
        ]

        session.query(SymbolRelationship).filter(
            SymbolRelationship.source_file_id == file_row.id
        ).delete(synchronize_session=False)

        if symbol_ids:
            session.query(SymbolRelationship).filter(
                SymbolRelationship.source_symbol_id.in_(symbol_ids)
            ).delete(synchronize_session=False)
            session.query(SymbolRelationship).filter(
                SymbolRelationship.target_symbol_id.in_(symbol_ids)
            ).delete(synchronize_session=False)
            session.query(Test).filter(
                Test.symbol_id.in_(symbol_ids)
            ).delete(synchronize_session=False)
            session.query(Embedding).filter(
                Embedding.symbol_id.in_(symbol_ids)
            ).delete(synchronize_session=False)

        session.query(Test).filter(
            Test.file_id == file_row.id
        ).delete(synchronize_session=False)
        session.query(Embedding).filter(
            Embedding.file_id == file_row.id
        ).delete(synchronize_session=False)
        session.query(Symbol).filter(
            Symbol.file_id == file_row.id
        ).delete(synchronize_session=False)

    def _delete_removed_files(
        self,
        session,
        repository: Repository,
        scanned_paths: set[str]
    ) -> int:

        query = session.query(File).filter(
            File.repository_id == repository.id
        )

        if scanned_paths:
            query = query.filter(
                ~File.path.in_(scanned_paths)
            )

        removed_files = query.all()
        removed = len(removed_files)

        for file_row in removed_files:
            session.delete(file_row)

        return removed

    def _resolve_symbol(
        self,
        session,
        repository: Repository,
        target_name: str | None,
        source_file: File | None = None
    ) -> Symbol | None:

        return self.relationship_builder.resolve_symbol(
            session,
            repository,
            target_name,
            source_file
        )

    def _resolve_pending_relationship_targets(
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

            target = self._resolve_symbol(
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

    def _create_file_embedding(
        self,
        session,
        repository: Repository,
        file_row: File,
        source_text: str
    ) -> None:

        session.add(
            Embedding(
                repository_id=repository.id,
                file_id=file_row.id,
                scope="file",
                content_hash=self.embedding_builder.content_hash(
                    source_text
                ),
                embedding_model=self.embedding_builder.model_name,
                dimensions=self.embedding_builder.dimensions,
                vector=self.embedding_builder.build(source_text),
                metadata_={
                    "path": file_row.path,
                    "language": file_row.language
                }
            )
        )

    def _create_symbol_embedding(
        self,
        session,
        repository: Repository,
        symbol: Symbol
    ) -> None:

        text = "\n".join(
            part for part in [
                symbol.qualified_name,
                symbol.symbol_type,
                symbol.signature or ""
            ]
            if part
        )

        session.add(
            Embedding(
                repository_id=repository.id,
                file_id=symbol.file_id,
                symbol_id=symbol.id,
                scope="symbol",
                content_hash=self.embedding_builder.content_hash(text),
                embedding_model=self.embedding_builder.model_name,
                dimensions=self.embedding_builder.dimensions,
                vector=self.embedding_builder.build(text),
                metadata_={
                    "qualified_name": symbol.qualified_name,
                    "symbol_type": symbol.symbol_type
                }
            )
        )

    def _ensure_baseline_repair_patterns(
        self,
        session,
        repository: Repository
    ) -> int:

        patterns = [
            {
                "name": "Missing import",
                "language": "python",
                "problem_signature": "NameError: name .* is not defined",
                "repair_strategy": "Resolve the referenced symbol from repository intelligence and add the narrowest valid import.",
                "confidence": 0.7
            },
            {
                "name": "Java missing bean",
                "language": "java",
                "problem_signature": "No qualifying bean of type .* available",
                "repair_strategy": "Find implementation symbols for the missing type and add or correct Spring component wiring.",
                "confidence": 0.65
            },
            {
                "name": "TypeScript missing export",
                "language": "typescript",
                "problem_signature": "Module .* has no exported member .*",
                "repair_strategy": "Resolve the target symbol and update the exporting barrel or import path.",
                "confidence": 0.65
            }
        ]

        created = 0

        for pattern in patterns:
            existing = (
                session.query(RepairPattern)
                .filter(
                    RepairPattern.repository_id == repository.id,
                    RepairPattern.language == pattern["language"],
                    RepairPattern.problem_signature == pattern[
                        "problem_signature"
                    ]
                )
                .one_or_none()
            )

            if existing:
                continue

            session.add(
                RepairPattern(
                    repository_id=repository.id,
                    name=pattern["name"],
                    language=pattern["language"],
                    problem_signature=pattern["problem_signature"],
                    repair_strategy=pattern["repair_strategy"],
                    confidence=pattern["confidence"],
                    examples=[]
                )
            )
            created += 1

        return created