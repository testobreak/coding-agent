# retrieval/vector_store.py

import faiss
import numpy as np


class VectorStore:

    def __init__(
        self,
        dimension: int
    ):

        self.dimension = dimension

        self.index = faiss.IndexFlatIP(
            dimension
        )

        self.chunks = []

    # =====================================================
    # NORMALIZATION
    # =====================================================

    def normalize(
        self,
        vector
    ):

        norm = np.linalg.norm(vector)

        if norm == 0:
            return vector

        return vector / norm

    # =====================================================
    # ADD
    # =====================================================

    def add(
        self,
        embedding,
        chunk
    ):

        embedding = self.normalize(
            embedding
        )

        embedding = np.array(
            [embedding],
            dtype=np.float32
        )

        self.index.add(embedding)

        self.chunks.append(chunk)

    # =====================================================
    # SEARCH
    # =====================================================

    def search(
        self,
        query_embedding,
        top_k=10,
        min_score=0.20
    ):

        if self.index.ntotal == 0:
            return []

        query_embedding = self.normalize(
            query_embedding
        )

        query_embedding = np.array(
            [query_embedding],
            dtype=np.float32
        )

        top_k = min(
            top_k,
            self.index.ntotal
        )

        scores, indices = self.index.search(
            query_embedding,
            top_k
        )

        results = []

        for score, idx in zip(
            scores[0],
            indices[0]
        ):

            if idx == -1:
                continue

            if score < min_score:
                continue

            results.append({

                "score": float(score),

                "chunk":
                    self.chunks[idx]
            })

        return results

    # =====================================================
    # INFO
    # =====================================================

    def total_vectors(self):

        return self.index.ntotal
