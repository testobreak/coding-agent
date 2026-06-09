EMBEDDING_WEIGHT = 0.55
GRAPH_WEIGHT = 0.20
FILE_WEIGHT = 0.15
RECENCY_WEIGHT = 0.10


def calculate_final_score(candidate) -> float:
    """
    Computes a weighted hybrid score combining:
      - Embedding match score (semantic match)
      - Graph connectivity score (structural relationships)
      - File importance (centrality of file in repo)
      - Recency (freshness of file modifications)
    """
    candidate.final_score = (
        candidate.embedding_score * EMBEDDING_WEIGHT
        + candidate.graph_score * GRAPH_WEIGHT
        + candidate.file_importance_score * FILE_WEIGHT
        + candidate.recency_score * RECENCY_WEIGHT
    )
    return candidate.final_score
