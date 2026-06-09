from repository_intelligence.db.connection import (
    Base,
    engine
)

# import ALL models
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.file import File
from repository_intelligence.models.symbol import (
    Symbol,
    Embedding,
    IndexJob,
    RepairPattern,
    SymbolRelationship,
    Test
)

Base.metadata.create_all(bind=engine)

print("Schema created")

