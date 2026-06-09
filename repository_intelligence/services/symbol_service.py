from sqlalchemy import func

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Embedding, Symbol


class SymbolService:

    def list_symbols(
        self,
        repository_id,
        symbol_type: str | None = None
    ):

        session = SessionLocal()

        try:
            query = session.query(Symbol).filter(
                Symbol.repository_id == repository_id
            )

            if symbol_type:
                query = query.filter(
                    Symbol.symbol_type == symbol_type
                )

            return query.order_by(
                Symbol.qualified_name
            ).all()

        finally:
            session.close()

    def upsert_embedding(
        self,
        repository_id,
        vector: list[float],
        content_hash: str,
        embedding_model: str,
        scope: str,
        file_id=None,
        symbol_id=None,
        metadata: dict | None = None
    ) -> Embedding:

        if not file_id and not symbol_id:
            raise ValueError(
                "file_id or symbol_id is required"
            )

        session = SessionLocal()

        try:
            query = session.query(Embedding).filter(
                Embedding.repository_id == repository_id,
                Embedding.scope == scope,
                Embedding.embedding_model == embedding_model
            )

            if symbol_id:
                query = query.filter(
                    Embedding.symbol_id == symbol_id
                )
            else:
                query = query.filter(
                    Embedding.file_id == file_id,
                    Embedding.symbol_id.is_(None)
                )

            embedding = query.one_or_none()

            if not embedding:
                embedding = Embedding(
                    repository_id=repository_id,
                    file_id=file_id,
                    symbol_id=symbol_id,
                    scope=scope,
                    embedding_model=embedding_model
                )
                session.add(embedding)

            embedding.content_hash = content_hash
            embedding.dimensions = len(vector)
            embedding.vector = vector
            embedding.metadata_ = metadata or {}
            embedding.updated_at = func.now()

            session.commit()
            session.refresh(embedding)

            return embedding

        except Exception:
            session.rollback()
            raise

        finally:
            session.close()
