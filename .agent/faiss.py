# NumPy-based mock/stub for faiss IndexFlatIP
import numpy as np
import pickle

class IndexFlatIP:
    def __init__(self, dimension: int):
        self.d = dimension
        self.vectors = None
        self.ntotal = 0

    def add(self, x: np.ndarray):
        # x is of shape (N, d) or (d,)
        x = np.atleast_2d(x).astype(np.float32)
        if self.vectors is None:
            self.vectors = x
        else:
            self.vectors = np.vstack([self.vectors, x])
        self.ntotal = self.vectors.shape[0]

    def search(self, x: np.ndarray, k: int):
        # x is query vectors of shape (M, d)
        x = np.atleast_2d(x).astype(np.float32)
        if self.vectors is None or self.ntotal == 0:
            return np.zeros((x.shape[0], 0), dtype=np.float32), np.full((x.shape[0], 0), -1, dtype=np.int64)
        
        # Calculate dot product: (M, d) x (d, ntotal) -> (M, ntotal)
        dots = np.dot(x, self.vectors.T)
        
        all_scores = []
        all_indices = []
        for i in range(dots.shape[0]):
            row = dots[i]
            # argsort returns indices in ascending order, reverse it
            sorted_idx = np.argsort(row)[::-1]
            top_k_idx = sorted_idx[:k]
            top_k_scores = row[top_k_idx]
            
            all_scores.append(top_k_scores)
            all_indices.append(top_k_idx)
            
        return np.array(all_scores, dtype=np.float32), np.array(all_indices, dtype=np.int64)

def write_index(index: IndexFlatIP, filename: str):
    with open(filename, 'wb') as f:
        pickle.dump(index, f)

def read_index(filename: str) -> IndexFlatIP:
    with open(filename, 'rb') as f:
        return pickle.load(f)
