import os
import sys
import math
from dataclasses import dataclass

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.indexer.embedding_builder import (
    EmbeddingBuilder
)
from repository_intelligence.models.file import File
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.symbol import Embedding, Symbol


@dataclass
class PersistedEmbedding:

    vector: list[float]
    chunk: dict


class DatabaseEmbeddingStore:

    def __init__(
        self,
        repo_root: str
    ):

        self.repo_root = os.path.abspath(repo_root)
        self.query_encoder = EmbeddingBuilder()

    def load(
        self
    ) -> list[PersistedEmbedding]:

        session = SessionLocal()

        try:
            repository = (
                session.query(Repository)
                .filter(Repository.root_path == self.repo_root)
                .one_or_none()
            )

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
                    chunk=self._chunk(
                        embedding,
                        file_row,
                        symbol
                    )
                )
                for embedding, file_row, symbol in rows
                if embedding.vector
            ]

        finally:
            session.close()

    def encode_query(
        self,
        query: str
    ) -> list[float]:

        return self.query_encoder.build(query)

    def search(
        self,
        persisted: list[PersistedEmbedding],
        query: str,
        top_k: int = 10,
        min_score: float = 0.20
    ) -> list[dict]:

        query_vector = self.encode_query(query)
        scored = []

        for item in persisted:
            score = self._cosine(
                query_vector,
                item.vector
            )

            if score < min_score:
                continue

            scored.append(
                {
                    "score": score,
                    "chunk": item.chunk
                }
            )

        scored.sort(
            key=lambda result: result["score"],
            reverse=True
        )

        return scored[:top_k]

    def _chunk(
        self,
        embedding: Embedding,
        file_row: File | None,
        symbol: Symbol | None
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
                "total_chunks": 1
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
            "total_chunks": 1
        }

    def _symbol_level(
        self,
        symbol_type: str
    ) -> int:

        if symbol_type in {"CLASS", "INTERFACE", "ENUM"}:
            return 2

        if symbol_type in {"METHOD", "FUNCTION"}:
            return 3

        return 4

    def _cosine(
        self,
        left: list[float],
        right: list[float]
    ) -> float:

        if not left or not right:
            return 0.0

        limit = min(
            len(left),
            len(right)
        )
        dot = sum(
            left[index] * right[index]
            for index in range(limit)
        )
        left_norm = math.sqrt(
            sum(value * value for value in left[:limit])
        )
        right_norm = math.sqrt(
            sum(value * value for value in right[:limit])
        )

        if not left_norm or not right_norm:
            return 0.0

        return dot / (left_norm * right_norm)
