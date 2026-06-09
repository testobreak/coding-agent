from contextlib import contextmanager
from dataclasses import dataclass
import math
import os

from sqlalchemy import text

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.indexer.embedding_builder import EmbeddingBuilder
from repository_intelligence.models.file import File
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.symbol import (
    Embedding,
    Symbol,
    SymbolRelationship,
    Test,
)
from repository_intelligence.services.repository_service import RepositoryService


@dataclass
class PersistedEmbedding:
    vector: list[float]
    chunk: dict


class RepositoryStore:
    """
    Adapter boundary between .agent orchestration and repository_intelligence.

    .agent code should depend on this class instead of importing
    repository_intelligence sessions, models, or services directly.
    """

    File = File
    Repository = Repository
    Symbol = Symbol
    SymbolRelationship = SymbolRelationship
    Test = Test

    def __init__(self, repo_root: str | None = None):
        self.repo_root = os.path.abspath(repo_root) if repo_root else None
        self.query_encoder = EmbeddingBuilder()

    @contextmanager
    def session(self):
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def ensure_modification_checkpoint_table(self) -> None:
        with self.session() as session:
            try:
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS modification_checkpoints (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        goal TEXT,
                        modified_files TEXT[],
                        validation_status TEXT NOT NULL,
                        rollback_reason TEXT
                    );
                """))
                session.commit()
            except Exception:
                session.rollback()
                raise

    def save_modification_checkpoint(
        self,
        checkpoint_id: str,
        task_id: str,
        created_at,
        goal: str,
        modified_files: list[str],
        validation_status: str,
        rollback_reason: str | None,
    ) -> None:
        with self.session() as session:
            try:
                exists = session.execute(
                    text(
                        "SELECT 1 FROM modification_checkpoints "
                        "WHERE id = :id"
                    ),
                    {"id": checkpoint_id},
                ).fetchone()

                params = {
                    "id": checkpoint_id,
                    "task_id": task_id,
                    "created_at": created_at,
                    "goal": goal,
                    "files": modified_files,
                    "status": validation_status,
                    "reason": rollback_reason,
                }

                if exists:
                    session.execute(
                        text("""
                            UPDATE modification_checkpoints
                            SET validation_status = :status,
                                rollback_reason = :reason,
                                modified_files = :files
                            WHERE id = :id
                        """),
                        params,
                    )
                else:
                    session.execute(
                        text("""
                            INSERT INTO modification_checkpoints (
                                id,
                                task_id,
                                created_at,
                                goal,
                                modified_files,
                                validation_status,
                                rollback_reason
                            )
                            VALUES (
                                :id,
                                :task_id,
                                :created_at,
                                :goal,
                                :files,
                                :status,
                                :reason
                            )
                        """),
                        params,
                    )

                session.commit()
            except Exception:
                session.rollback()
                raise

    def ensure_memory_tables(self) -> None:
        with self.session() as session:
            try:
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS task_summaries (
                        id SERIAL PRIMARY KEY,
                        task_id TEXT,
                        summary TEXT,
                        start_step INTEGER,
                        end_step INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS task_events (
                        id SERIAL PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        event_data JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_task_events_task_id
                    ON task_events(task_id);
                """))
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_task_events_type
                    ON task_events(event_type);
                """))
                session.commit()
            except Exception:
                session.rollback()
                raise

    def record_task_event(
        self,
        task_id: str,
        event_type: str,
        event_data_json: str,
        session=None,
    ) -> None:
        sql = text("""
            INSERT INTO task_events (
                task_id,
                event_type,
                event_data,
                created_at
            )
            VALUES (
                :task_id,
                :event_type,
                CAST(:event_data AS jsonb),
                NOW()
            )
        """)
        params = {
            "task_id": task_id,
            "event_type": event_type,
            "event_data": event_data_json,
        }

        if session is not None:
            session.execute(sql, params)
            session.flush()
            return

        with self.session() as local_session:
            try:
                local_session.execute(sql, params)
                local_session.commit()
            except Exception:
                local_session.rollback()
                raise

    def save_task_summary(
        self,
        task_id: str,
        summary: str,
        start_step: int,
        end_step: int,
    ) -> None:
        with self.session() as session:
            try:
                session.execute(
                    text("""
                        INSERT INTO task_summaries (
                            task_id,
                            summary,
                            start_step,
                            end_step,
                            created_at
                        )
                        VALUES (
                            :task_id,
                            :summary,
                            :start_step,
                            :end_step,
                            NOW()
                        )
                    """),
                    {
                        "task_id": task_id,
                        "summary": summary,
                        "start_step": start_step,
                        "end_step": end_step,
                    },
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    def scan_repository(self, repo_root: str | None = None) -> dict:
        return RepositoryService().scan_repository(repo_root or self.repo_root)

    def get_repository(self, session, repo_root: str):
        root_path = os.path.abspath(repo_root)
        return (
            session.query(Repository)
            .filter(Repository.root_path == root_path)
            .one_or_none()
        )

    def load_persisted_embeddings(self) -> list[PersistedEmbedding]:
        if not self.repo_root:
            return []

        with self.session() as session:
            repository = self.get_repository(session, self.repo_root)

            if not repository:
                return []

            rows = (
                session.query(Embedding, File, Symbol)
                .outerjoin(File, Embedding.file_id == File.id)
                .outerjoin(Symbol, Embedding.symbol_id == Symbol.id)
                .filter(Embedding.repository_id == repository.id)
                .all()
            )

            return [
                PersistedEmbedding(
                    vector=list(embedding.vector),
                    chunk=self._embedding_chunk(embedding, file_row, symbol),
                )
                for embedding, file_row, symbol in rows
                if embedding.vector
            ]

    def encode_query(self, query: str) -> list[float]:
        return self.query_encoder.build(query)

    def search_embeddings(
        self,
        persisted: list[PersistedEmbedding],
        query: str,
        top_k: int = 10,
        min_score: float = 0.20,
    ) -> list[dict]:
        query_vector = self.encode_query(query)
        scored = []

        for item in persisted:
            score = self._cosine(query_vector, item.vector)

            if score < min_score:
                continue

            scored.append({"score": score, "chunk": item.chunk})

        scored.sort(key=lambda result: result["score"], reverse=True)
        return scored[:top_k]

    def _embedding_chunk(
        self,
        embedding: Embedding,
        file_row: File | None,
        symbol: Symbol | None,
    ) -> dict:
        file_path = file_row.path if file_row else ""

        if symbol:
            return {
                "chunk_id": f"db:symbol:{symbol.id}",
                "source": "database",
                "embedding_id": str(embedding.id),
                "file": file_path,
                "name": symbol.name,
                "symbol": symbol.qualified_name,
                "type": symbol.symbol_type,
                "parent": str(symbol.parent_symbol_id or ""),
                "start_line": symbol.start_line,
                "end_line": symbol.end_line,
                "content": symbol.signature or "",
                "code": symbol.signature or "",
                "level": self._symbol_level(symbol.symbol_type),
                "chunk_index": 0,
                "total_chunks": 1,
            }

        return {
            "chunk_id": f"db:file:{file_row.id if file_row else embedding.id}",
            "source": "database",
            "embedding_id": str(embedding.id),
            "file": file_path,
            "name": file_path,
            "symbol": "",
            "type": "FILE",
            "parent": "",
            "start_line": 1,
            "end_line": 1,
            "content": file_path,
            "code": file_path,
            "level": 1,
            "chunk_index": 0,
            "total_chunks": 1,
        }

    def _symbol_level(self, symbol_type: str) -> int:
        if symbol_type in {"CLASS", "INTERFACE", "ENUM"}:
            return 2

        if symbol_type in {"METHOD", "FUNCTION"}:
            return 3

        return 4

    def _cosine(self, left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0

        limit = min(len(left), len(right))
        dot = sum(left[index] * right[index] for index in range(limit))
        left_norm = math.sqrt(sum(value * value for value in left[:limit]))
        right_norm = math.sqrt(sum(value * value for value in right[:limit]))

        if not left_norm or not right_norm:
            return 0.0

        return dot / (left_norm * right_norm)
