from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from repository_intelligence.db.connection import Base


class File(Base):

    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "path"
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

    path = Column(Text, nullable=False)
    language = Column(Text, nullable=False)
    file_hash = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    repository = relationship(
        "Repository",
        back_populates="files"
    )

    symbols = relationship(
        "Symbol",
        back_populates="file",
        cascade="all, delete-orphan"
    )
