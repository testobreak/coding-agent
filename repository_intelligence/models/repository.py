from sqlalchemy import Column, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from repository_intelligence.db.connection import Base


class Repository(Base):

    __tablename__ = "repositories"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    name = Column(Text, nullable=False)
    root_path = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    files = relationship(
        "File",
        back_populates="repository",
        cascade="all, delete-orphan"
    )
