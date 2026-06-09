# retrieval/hierarchy/hierarchical_store.py
#
# Per-level FAISS vector stores for hierarchical retrieval.
#
# Level 0 — Repository   (one embedding per repo — not used for search, anchor only)
# Level 1 — File         (one embedding per source file)
# Level 2 — Class        (one embedding per class / interface / enum)
# Level 3 — Method       (one embedding per method / function)
# Level 4 — Chunk        (sliding-window fallback, same as flat retrieval)
#
# Each level has its own FAISS IndexFlatIP (inner product on normalized
# embeddings = cosine similarity).  A chunk stored at level N carries a
# `level` field so downstream code can reason about granularity.
#

import os
import pickle
import faiss
import numpy as np
from typing import Dict, List, Optional, Any, Tuple

LEVEL_NAMES = {0: "repo", 1: "file", 2: "class", 3: "method", 4: "chunk"}
NUM_LEVELS = 5


class LevelStore:
    """Single-level FAISS store: one index + matching chunk list."""

    def __init__(self, dimension: int, level: int):
        self.level = level
        self.level_name = LEVEL_NAMES.get(level, str(level))
        self.index = faiss.IndexFlatIP(dimension)
        self.chunks: List[Dict[str, Any]] = []

    def add(self, embedding: np.ndarray, chunk: Dict[str, Any]) -> None:
        vec = embedding.reshape(1, -1).astype(np.float32)
        self.index.add(vec)
        chunk = dict(chunk)
        chunk["level"] = self.level
        chunk["level_name"] = self.level_name
        self.chunks.append(chunk)

    def search(
        self, embedding: np.ndarray, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        if self.index.ntotal == 0:
            return []
        k = min(top_k, self.index.ntotal)
        vec = embedding.reshape(1, -1).astype(np.float32)
        scores, indices = self.index.search(vec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            results.append({
                "score": float(score),
                "chunk": self.chunks[idx],
            })
        return results

    def size(self) -> int:
        return self.index.ntotal


class HierarchicalStore:
    """
    Wraps NUM_LEVELS LevelStore instances.
    Persists each level independently to .cache/hier_level_N.{faiss,pkl}.
    """

    CACHE_DIR = ".cache"

    def __init__(self, dimension: int):
        self.dimension = dimension
        self.levels: List[LevelStore] = [
            LevelStore(dimension, lvl) for lvl in range(NUM_LEVELS)
        ]

    # ----------------------------------------------------------
    # ADD
    # ----------------------------------------------------------

    def add(self, level: int, embedding: np.ndarray, chunk: Dict) -> None:
        self.levels[level].add(embedding, chunk)

    # ----------------------------------------------------------
    # SEARCH
    # ----------------------------------------------------------

    def search_level(
        self, level: int, embedding: np.ndarray, top_k: int = 5
    ) -> List[Dict]:
        return self.levels[level].search(embedding, top_k)

    def search_all(
        self, embedding: np.ndarray, top_k_per_level: int = 3
    ) -> List[Dict]:
        """Search every level and merge results."""
        merged = []
        for lvl in self.levels:
            merged.extend(lvl.search(embedding, top_k_per_level))
        return merged

    # ----------------------------------------------------------
    # PERSIST
    # ----------------------------------------------------------

    def save(self) -> None:
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        for lvl in self.levels:
            faiss.write_index(
                lvl.index,
                os.path.join(self.CACHE_DIR, f"hier_level_{lvl.level}.faiss"),
            )
            with open(
                os.path.join(self.CACHE_DIR, f"hier_level_{lvl.level}.pkl"), "wb"
            ) as f:
                pickle.dump(lvl.chunks, f)
        print(
            f"[HierarchicalStore] Saved "
            + ", ".join(
                f"L{l.level}:{l.size()}" for l in self.levels
            )
        )

    def load(self) -> bool:
        """Load all levels. Returns True if all level files existed."""
        all_loaded = True
        for lvl in self.levels:
            faiss_path = os.path.join(self.CACHE_DIR, f"hier_level_{lvl.level}.faiss")
            pkl_path = os.path.join(self.CACHE_DIR, f"hier_level_{lvl.level}.pkl")
            if not (os.path.exists(faiss_path) and os.path.exists(pkl_path)):
                all_loaded = False
                continue
            try:
                lvl.index = faiss.read_index(faiss_path)
                with open(pkl_path, "rb") as f:
                    lvl.chunks = pickle.load(f)
                    # Patch level metadata if missing
                    for c in lvl.chunks:
                        c.setdefault("level", lvl.level)
                        c.setdefault("level_name", lvl.level_name)
            except Exception as e:
                print(f"[HierarchicalStore] Load error L{lvl.level}: {e}")
                all_loaded = False
        return all_loaded

    def cache_exists(self) -> bool:
        return all(
            os.path.exists(os.path.join(self.CACHE_DIR, f"hier_level_{l}.faiss"))
            and os.path.exists(os.path.join(self.CACHE_DIR, f"hier_level_{l}.pkl"))
            for l in range(NUM_LEVELS)
        )

    def sizes(self) -> Dict[str, int]:
        return {f"L{l.level}_{l.level_name}": l.size() for l in self.levels}
