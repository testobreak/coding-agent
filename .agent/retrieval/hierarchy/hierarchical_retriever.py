# retrieval/hierarchy/hierarchical_retriever.py
#
# Cascading retrieval:
#
#   Query
#    ↓
#   Level 1 (Repository) search  → top candidate modules (e.g. auth, payroll)
#    ↓
#   Level 2 (File) search        → filter files to candidate modules
#    ↓
#   Level 3 (Symbol) search      → filter symbols to candidate files
#    ↓
#   Level 4 (Chunk) search       → filter generic chunks to candidate files
#    ↓
#   Merge + deduplicate + weight scores → top_k results
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
        symbol_top_k: int = 10,
        chunk_top_k: int = 8,
    ):
        self.store = store
        self.embedding_engine = embedding_engine
        self.file_top_k = file_top_k
        self.symbol_top_k = symbol_top_k
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
        Cascade search: Repository -> File -> Symbol -> Chunk.
        Returns top_k results as {"score": float, "chunk": dict} dicts.
        """
        embedding = self.embedding_engine.embed_text(query)

        # --- Level 1: Repository Summaries ---
        # Search modules (e.g. auth, payroll, leave)
        repo_results = self.store.search_level(1, embedding, 3)
        candidate_repos = {r["chunk"]["name"] for r in repo_results}

        # --- Level 2: File Summaries (filtered by candidate modules) ---
        file_results_raw = self.store.search_level(2, embedding, self.file_top_k * 2)
        file_results = []
        for r in file_results_raw:
            f = r["chunk"].get("file", "")
            parts = [p for p in f.split("/") if p]
            mod = parts[0] if len(parts) > 1 else "core"
            if mod in candidate_repos:
                file_results.append(r)
        # Fallback if no files matched the modules
        if not file_results:
            file_results = file_results_raw[:self.file_top_k]
        candidate_files = {r["chunk"]["file"] for r in file_results}

        # --- Level 3: Symbol Graph (filtered by candidate files) ---
        symbol_results_raw = self.store.search_level(3, embedding, self.symbol_top_k * 2)
        symbol_results = [
            r for r in symbol_results_raw
            if r["chunk"].get("file") in candidate_files
        ] or symbol_results_raw[:self.symbol_top_k]

        # --- Level 4: Chunk Retrieval (filtered by candidate files) ---
        chunk_results_raw = self.store.search_level(4, embedding, self.chunk_top_k * 2)
        chunk_results = [
            r for r in chunk_results_raw
            if r["chunk"].get("file") in candidate_files
        ] or chunk_results_raw[:self.chunk_top_k]

        # --- Merge all levels ---
        merged = self._merge(
            repo_results, file_results, symbol_results, chunk_results
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
            name = {1: "Repo", 2: "File", 3: "Symbol", 4: "Chunk"}[level]
            results = self.store.search_level(level, embedding, top_k)
            print(f"  Level {level} ({name}): {len(results)} results")
            for r in results[:3]:
                chunk = r["chunk"]
                print(
                    f"    {chunk.get('file', '?')} :: "
                    f"{chunk.get('name', '?')} "
                    f"(score={r['score']:.3f})"
                )
