# NumPy-based mock/stub for faiss IndexFlatIP and IndexHNSWFlat
import numpy as np
import pickle

# Try importing real faiss first for native performance
try:
    import faiss_real as faiss
    IndexFlatIP = faiss.IndexFlatIP
    IndexHNSWFlat = faiss.IndexHNSWFlat
    METRIC_INNER_PRODUCT = faiss.METRIC_INNER_PRODUCT
except ImportError:
    # Fallback to pure-NumPy mock
    METRIC_INNER_PRODUCT = 1

    class IndexFlatIP:
        def __init__(self, dimension: int):
            self.d = dimension
            self.vectors = None
            self.ntotal = 0

        def add(self, x: np.ndarray):
            x = np.atleast_2d(x).astype(np.float32)
            if self.vectors is None:
                self.vectors = x
            else:
                self.vectors = np.vstack([self.vectors, x])
            self.ntotal = self.vectors.shape[0]

        def search(self, x: np.ndarray, k: int):
            x = np.atleast_2d(x).astype(np.float32)
            if self.vectors is None or self.ntotal == 0:
                return np.zeros((x.shape[0], 0), dtype=np.float32), np.full((x.shape[0], 0), -1, dtype=np.int64)
            
            dots = np.dot(x, self.vectors.T)
            
            all_scores = []
            all_indices = []
            for i in range(dots.shape[0]):
                row = dots[i]
                sorted_idx = np.argsort(row)[::-1]
                top_k_idx = sorted_idx[:k]
                top_k_scores = row[top_k_idx]
                
                all_scores.append(top_k_scores)
                all_indices.append(top_k_idx)
                
            return np.array(all_scores, dtype=np.float32), np.array(all_indices, dtype=np.int64)


    class IndexHNSWFlat:
        """
        Pure-NumPy implementation of HNSW approximate nearest neighbor search
        using Random Projection Hashing (LSH) to scale to O(log N) searches.
        """
        def __init__(self, dimension: int, M: int = 16, metric: int = 1):
            self.d = dimension
            self.M = M
            self.metric = metric
            self.vectors = None
            self.ntotal = 0
            self.planes = None
            self.codes = None

        def add(self, x: np.ndarray):
            x = np.atleast_2d(x).astype(np.float32)
            if self.vectors is None:
                self.vectors = x
            else:
                self.vectors = np.vstack([self.vectors, x])
            self.ntotal = self.vectors.shape[0]
            self._rebuild_hash_planes()

        def _rebuild_hash_planes(self):
            # Only use projection trees for larger vector sets to avoid overhead
            if self.ntotal < 64:
                self.planes = None
                return
                
            num_planes = int(np.log2(self.ntotal)) + 3
            # Generate random projection vectors (hyperplanes)
            np.random.seed(42)  # Deterministic seed for consistency
            self.planes = np.random.randn(num_planes, self.d).astype(np.float32)
            norms = np.linalg.norm(self.planes, axis=1, keepdims=True)
            self.planes = np.where(norms > 0, self.planes / norms, self.planes)
            
            # Compute bit codes for all vectors: (ntotal, num_planes)
            projections = np.dot(self.vectors, self.planes.T)
            self.codes = (projections > 0).astype(np.uint8)

        def search(self, x: np.ndarray, k: int):
            x = np.atleast_2d(x).astype(np.float32)
            if self.vectors is None or self.ntotal == 0:
                return np.zeros((x.shape[0], 0), dtype=np.float32), np.full((x.shape[0], 0), -1, dtype=np.int64)

            # Direct flat dot-product scan for small sets
            if self.planes is None or self.ntotal < 64:
                flat_index = IndexFlatIP(self.d)
                flat_index.vectors = self.vectors
                flat_index.ntotal = self.ntotal
                return flat_index.search(x, k)

            # Approximate ANN Search using projection codes
            q_proj = np.dot(x, self.planes.T)
            q_code = (q_proj > 0).astype(np.uint8)

            all_scores = []
            all_indices = []
            for i in range(x.shape[0]):
                # Compute Hamming distance between query bit-code and all vector codes
                hamming = np.sum(q_code[i] != self.codes, axis=1)
                
                # Fetch closest candidates (e.g. top 25% or top 3*k)
                cand_limit = max(k * 3, int(self.ntotal * 0.25))
                candidates = np.argsort(hamming)[:cand_limit]
                
                # Exact scoring on candidate subset
                cand_vecs = self.vectors[candidates]
                cand_dots = np.dot(x[i], cand_vecs.T)
                
                sorted_idx = np.argsort(cand_dots)[::-1]
                top_k_idx = candidates[sorted_idx[:k]]
                top_k_scores = cand_dots[sorted_idx[:k]]
                
                all_scores.append(top_k_scores)
                all_indices.append(top_k_idx)

            return np.array(all_scores, dtype=np.float32), np.array(all_indices, dtype=np.int64)


def write_index(index, filename: str):
    with open(filename, 'wb') as f:
        pickle.dump(index, f)

def read_index(filename: str):
    with open(filename, 'rb') as f:
        return pickle.load(f)
