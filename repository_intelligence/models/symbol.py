from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from repository_intelligence.db.connection import Base


class Symbol(Base):

    __tablename__ = "symbols"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "qualified_name",
            "symbol_type"
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    repository_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False
    )

    file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False
    )

    name = Column(Text, nullable=False)
    qualified_name = Column(Text, nullable=False)
    symbol_type = Column(Text, nullable=False)
    parent_symbol_id = Column(
        UUID(as_uuid=True),
        ForeignKey("symbols.id", ondelete="CASCADE")
    )
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    signature = Column(Text)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    source_hash = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    file = relationship(
        "File",
        back_populates="symbols"
    )

    parent = relationship(
        "Symbol",
        remote_side=[id]
    )


class SymbolRelationship(Base):

    __tablename__ = "symbol_relationships"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    repository_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False
    )

    source_symbol_id = Column(
        UUID(as_uuid=True),
        ForeignKey("symbols.id", ondelete="CASCADE")
    )

    target_symbol_id = Column(
        UUID(as_uuid=True),
        ForeignKey("symbols.id", ondelete="CASCADE")
    )

    source_file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE")
    )

    target_name = Column(Text)
    relationship_type = Column(Text, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False, default=1.0)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Embedding(Base):

    __tablename__ = "embeddings"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    repository_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False
    )

    file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE")
    )

    symbol_id = Column(
        UUID(as_uuid=True),
        ForeignKey("symbols.id", ondelete="CASCADE")
    )

    scope = Column(Text, nullable=False)
    content_hash = Column(Text, nullable=False)
    embedding_model = Column(Text, nullable=False)
    dimensions = Column(Integer, nullable=False)
    vector = Column(JSONB, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class IndexJob(Base):

    __tablename__ = "index_jobs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    repository_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False
    )

    status = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    scanned_files = Column(Integer, nullable=False, default=0)
    changed_files = Column(Integer, nullable=False, default=0)
    changed_symbols = Column(Integer, nullable=False, default=0)
    error = Column(Text)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)


class Test(Base):

    __tablename__ = "tests"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "file_id",
            "name"
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    repository_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False
    )

    file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False
    )

    symbol_id = Column(
        UUID(as_uuid=True),
        ForeignKey("symbols.id", ondelete="SET NULL")
    )

    name = Column(Text, nullable=False)
    framework = Column(Text)
    target_symbol_id = Column(
        UUID(as_uuid=True),
        ForeignKey("symbols.id", ondelete="SET NULL")
    )
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class RepairPattern(Base):

    __tablename__ = "repair_patterns"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    repository_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE")
    )

    name = Column(Text, nullable=False)
    language = Column(Text)
    problem_signature = Column(Text, nullable=False)
    repair_strategy = Column(Text, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False, default=0.5)
    examples = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
