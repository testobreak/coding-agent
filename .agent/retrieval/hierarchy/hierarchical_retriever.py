# retrieval/hierarchy/hierarchical_retriever.py
#
# Cascading retrieval:
#
#   Query
#    ↓
#   Level 1 (File) search   → top K files
#    ↓
#   Level 2 (Class) search  → filter to classes in top files
#    ↓
#   Level 3 (Method) search → filter to methods in top classes
#    ↓
#   Level 4 (Chunk) search  → final fine-grained context
#    ↓
#   Merge + deduplicate + rerank → results
#
# Why cascade?
#   - File-level search narrows the search space first (O(N_files) not O(N_chunks))
#   - Class + method levels get precise results inside the right files
#   - Chunk level handles languages without class/method AST (YAML, CSS, markdown)
#
# Falls back to flat FAISS search if hierarchical store is not available.
#

import numpy as np
from typing import List, Dict, Any, Optional

from retrieval.hierarchy.hierarchical_store import HierarchicalStore
from retrieval.embedding_engine import EmbeddingEngine


class HierarchicalRetriever:
    """
    Cascading hierarchical retrieval over a HierarchicalStore.

    Usage:
        retriever = HierarchicalRetriever(store, embedding_engine)
        results = retriever.search(query="find salary service", top_k=8)
    """

    def __init__(
        self,
        store: HierarchicalStore,
        embedding_engine: EmbeddingEngine,
        file_top_k: int = 5,
        class_top_k: int = 8,
        method_top_k: int = 10,
        chunk_top_k: int = 8,
    ):
        self.store = store
        self.embedding_engine = embedding_engine
        self.file_top_k = file_top_k
        self.class_top_k = class_top_k
        self.method_top_k = method_top_k
        self.chunk_top_k = chunk_top_k

    # =========================================================
    # MAIN
    # =========================================================

    def search(
        self,
        query: str,
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Cascade search: file → class → method → chunk.
        Returns top_k results as {"score": float, "chunk": dict} dicts.
        """
        embedding = self.embedding_engine.embed_text(query)

        # --- Level 1: File ---
        file_results = self.store.search_level(1, embedding, self.file_top_k)
        candidate_files = {r["chunk"]["file"] for r in file_results}

        # --- Level 2: Class (filtered by candidate files) ---
        class_results_raw = self.store.search_level(2, embedding, self.class_top_k * 2)
        class_results = [
            r for r in class_results_raw
            if r["chunk"].get("file") in candidate_files
        ] or class_results_raw[:self.class_top_k]
        candidate_classes = {r["chunk"].get("name") for r in class_results}

        # --- Level 3: Method (filtered by candidate classes) ---
        method_results_raw = self.store.search_level(3, embedding, self.method_top_k * 2)
        method_results = [
            r for r in method_results_raw
            if r["chunk"].get("parent") in candidate_classes
            or r["chunk"].get("file") in candidate_files
        ] or method_results_raw[:self.method_top_k]

        # --- Level 4: Chunk (fine-grained fallback, also filtered by files) ---
        chunk_results_raw = self.store.search_level(4, embedding, self.chunk_top_k * 2)
        chunk_results = [
            r for r in chunk_results_raw
            if r["chunk"].get("file") in candidate_files
        ] or chunk_results_raw[:self.chunk_top_k]

        # --- Merge all levels ---
        merged = self._merge(
            file_results, class_results, method_results, chunk_results
        )

        # --- Deduplicate by chunk_id ---
        seen: set = set()
        deduped = []
        for item in merged:
            cid = item["chunk"].get("chunk_id")
            if cid in seen:
                continue
            seen.add(cid)
            deduped.append(item)

        # --- Sort by score descending ---
        deduped.sort(key=lambda x: x["score"], reverse=True)

        return deduped[:top_k]

    # =========================================================
    # MULTI-QUERY
    # =========================================================

    def search_multi(
        self,
        queries: List[str],
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """Run cascading search for each query, merge results."""
        merged = []
        seen: set = set()

        for query in queries:
            results = self.search(query, top_k=top_k)
            for item in results:
                cid = item["chunk"].get("chunk_id")
                if cid in seen:
                    continue
                seen.add(cid)
                merged.append(item)

        merged.sort(key=lambda x: x["score"], reverse=True)
        return merged[:top_k]

    # =========================================================
    # MERGE
    # =========================================================

    def _merge(self, *result_lists) -> List[Dict]:
        """
        Merge result lists from different levels with level-based score weights.
        Higher-specificity levels (method, chunk) get slight boosts.
        """
        weights = {1: 0.6, 2: 0.8, 3: 1.0, 4: 0.9}

        merged = []
        for result_list in result_lists:
            for item in result_list:
                level = item["chunk"].get("level", 4)
                weighted_score = item["score"] * weights.get(level, 0.7)
                merged.append({
                    "score": weighted_score,
                    "chunk": item["chunk"],
                })

        return merged

    # =========================================================
    # DIAGNOSTICS
    # =========================================================

    def explain(self, query: str, top_k: int = 5) -> None:
        """Print a human-readable explanation of which levels matched."""
        embedding = self.embedding_engine.embed_text(query)
        print(f"\n[HierarchicalRetriever] Query: '{query}'")
        for level in [1, 2, 3, 4]:
            name = {1: "File", 2: "Class", 3: "Method", 4: "Chunk"}[level]
            results = self.store.search_level(level, embedding, top_k)
            print(f"  Level {level} ({name}): {len(results)} results")
            for r in results[:3]:
                chunk = r["chunk"]
                print(
                    f"    {chunk.get('file', '?')} :: "
                    f"{chunk.get('name', '?')} "
                    f"(score={r['score']:.3f})"
                )
