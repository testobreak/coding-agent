from dataclasses import dataclass
from typing import Any


@dataclass
class RetrievalCandidate:
    symbol_id: Any
    embedding_score: float = 0.0
    graph_score: float = 0.0
    recency_score: float = 0.0
    file_importance_score: float = 0.0
    final_score: float = 0.0
    chunk: dict = None
