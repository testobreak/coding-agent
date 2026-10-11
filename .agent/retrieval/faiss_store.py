# retrieval/faiss_store.py
import os
import pickle
from pathlib import Path
import faiss
import numpy as np
from retrieval.vector_store import VectorStore

class FaissVectorStore(VectorStore):
    def __init__(self, dim: int, index_path: str = ".cache/vector_store"):
        self.dim = dim
        self.index_path = Path(index_path)
        self.mapping = {}  # index -> chunk_id
        self.chunks_map = {}  # chunk_id -> chunk

        # Build optimized HNSW index parameters
        try:
            self.index = faiss.IndexHNSWFlat(self.dim, 32, faiss.METRIC_INNER_PRODUCT)
            self.index.hnsw.efConstruction = 200
            self.index.hnsw.efSearch = 64
        except Exception:
            self.index = faiss.IndexFlatIP(self.dim)

    def add_embeddings(self, chunk_ids, vectors, chunks):
        if not vectors:
            return
        vectors = np.array(vectors).astype("float32")
        # Normalize vectors for METRIC_INNER_PRODUCT (cosine similarity)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = np.where(norms > 0, vectors / norms, vectors)

        start = len(self.mapping)
        for i, cid in enumerate(chunk_ids):
            self.mapping[start + i] = cid
            self.chunks_map[cid] = chunks[i]

        self.index.add(vectors)

    def search(self, query_vector, k=20):
        if self.index.ntotal == 0:
            return []
        query = np.array([query_vector]).astype("float32")
        # Normalize query vector
        q_norm = np.linalg.norm(query)
        if q_norm > 0:
            query = query / q_norm

        top_k = min(k, self.index.ntotal)
        distances, indices = self.index.search(query, top_k)

        results = []
        for score, idx in zip(distances[0], indices[0]):
            if idx == -1 or idx not in self.mapping:
                continue
            cid = self.mapping[idx]
            results.append({
                "score": float(score),
                "chunk": self.chunks_map[cid]
            })
        return results

    def save(self, file_path: str = None):
        path = Path(file_path) if file_path else self.index_path
        index_file = str(path) + ".index"
        meta_file = str(path) + ".meta"

        faiss.write_index(self.index, index_file)
        with open(meta_file, "wb") as f:
            pickle.dump((self.dim, self.mapping, self.chunks_map), f)

    def load(self, file_path: str = None):
        path = Path(file_path) if file_path else self.index_path
        index_file = str(path) + ".index"
        meta_file = str(path) + ".meta"

        if os.path.exists(index_file) and os.path.exists(meta_file):
            self.index = faiss.read_index(index_file)
            with open(meta_file, "rb") as f:
                self.dim, self.mapping, self.chunks_map = pickle.load(f)
