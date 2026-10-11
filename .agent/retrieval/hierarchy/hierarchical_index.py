# retrieval/hierarchy/hierarchical_index.py
#
# Builds embeddings at 4 levels:
#
#   Level 1 — Repository : module/subfolder descriptions (e.g. auth, payroll, leave)
#   Level 2 — File       : one embedding per source file (aggregated summary)
#   Level 3 — Symbol     : class, method, function, or constructor definitions
#   Level 4 — Chunk      : sliding-window generic chunks (same as flat)
#

import time
import os
import numpy as np
from collections import defaultdict
from typing import List, Dict, Any

from retrieval.hierarchy.hierarchical_store import HierarchicalStore
from retrieval.embedding_engine import EmbeddingEngine
from retrieval.index_tracker import IndexTracker

# Chunk type → level mapping
_TYPE_TO_LEVEL = {
    "ClassDef":     3,
    "InterfaceDef": 3,
    "EnumDef":      3,
    "MethodDef":    3,
    "FunctionDef":  3,
    "ConstructorDef": 3,
}
_DEFAULT_CHUNK_LEVEL = 4


class HierarchicalIndex:
    """
    Builds and queries the 4-level hierarchical vector store.

    Usage:
        idx = HierarchicalIndex(embedding_engine)
        idx.build(chunks)          # chunks from RepoChunker
        idx.save()
        # or:
        idx.load()                 # from cache
    """

    def __init__(self, embedding_engine: EmbeddingEngine = None):
        self.embedding_engine = embedding_engine or EmbeddingEngine()
        self.store: HierarchicalStore = None   # set after build() / load()
        self.tracker = IndexTracker()

    # =========================================================
    # BUILD
    # =========================================================

    def build(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Classify chunks into 4 levels: repository summaries, file summaries,
        symbols, and generic chunks, then embed and populate HierarchicalStore.
        """
        start = time.time()
        print("[HierarchicalIndex] Building hierarchical embeddings…")

        all_texts: List[str] = []
        all_levels: List[int] = []
        all_chunks: List[Dict] = []

        # --- Step 1: Repository summaries (Level 1) ---
        repo_chunks = self._make_repo_chunks(chunks)
        for rc in repo_chunks:
            all_texts.append(self._build_search_text(rc))
            all_levels.append(1)
            all_chunks.append(rc)

        # --- Step 2: File summaries (Level 2) ---
        by_file: Dict[str, List[Dict]] = defaultdict(list)
        for chunk in chunks:
            by_file[chunk.get("file", "__unknown__")].append(chunk)

        for file_path, file_chunks in by_file.items():
            file_chunk = self._make_file_chunk(file_path, file_chunks)
            all_texts.append(self._build_search_text(file_chunk))
            all_levels.append(2)
            all_chunks.append(file_chunk)

        # --- Step 3: Symbols (Level 3) & Chunks (Level 4) ---
        for chunk in chunks:
            chunk_type = chunk.get("type", "")
            level = _TYPE_TO_LEVEL.get(chunk_type, _DEFAULT_CHUNK_LEVEL)
            all_texts.append(self._build_search_text(chunk))
            all_levels.append(level)
            all_chunks.append(chunk)

        # --- Step 4: Embed all at once ---
        print(f"[HierarchicalIndex] Embedding {len(all_texts)} items…")
        embeddings = self.embedding_engine.embed_batch(all_texts)

        dimension = embeddings.shape[1]
        self.store = HierarchicalStore(dimension)

        for embedding, level, chunk in zip(embeddings, all_levels, all_chunks):
            self.store.add(level, embedding, chunk)

        elapsed = time.time() - start
        print(
            f"[HierarchicalIndex] Built in {elapsed:.2f}s — "
            + str(self.store.sizes())
        )

    # =========================================================
    # SAVE / LOAD
    # =========================================================

    def save(self) -> None:
        if self.store:
            self.store.save()

    def load(self) -> bool:
        """Restore from cache. Returns True on success."""
        # Peek at dimension from existing flat index
        import faiss, os
        flat_path = ".cache/code_index.faiss"
        if not os.path.exists(flat_path):
            return False
        try:
            idx = faiss.read_index(flat_path)
            dimension = idx.d
        except Exception:
            return False

        self.store = HierarchicalStore(dimension)
        loaded = self.store.load()
        if loaded:
            print(f"[HierarchicalIndex] Loaded from cache — {self.store.sizes()}")
        return loaded

    def cache_exists(self) -> bool:
        if self.store:
            return self.store.cache_exists()
        import os
        return os.path.exists(".cache/hier_level_1.faiss")

    # =========================================================
    # HELPERS
    # =========================================================

    def _make_repo_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Group chunks by their top-level directory (module) under repo root
        by_module = defaultdict(list)
        for chunk in chunks:
            fpath = chunk.get("file", "")
            if not fpath:
                continue
            # Get the top-level directory name under repo root
            parts = [p for p in fpath.split("/") if p]
            if len(parts) > 1:
                module_name = parts[0]
            else:
                module_name = "core"
            by_module[module_name].append(chunk)

        # Pre-defined high-level descriptions/summaries for typical software domains
        descriptions = {
            "auth": "Authentication, authorization, user roles, security access control, and user session management.",
            "payroll": "Employee payroll processing, salary calculations, tax deductions, bonuses, payslip generation, and benefits management.",
            "leave": "Employee leave request submission, balance validation, leave approval workflows, and leave history tracker.",
            "employee": "Employee profiles, hiring, personal details, contact info, job roles, department assignment, and team management.",
            "performance": "Employee performance evaluations, KPIs, feedback collection, reviews, and appraisal tracking.",
            "core": "Core shared services, utility classes, DB connection, standard helper functions, and base repository wrappers.",
            "utils": "Common helper utilities, date-time formatters, loggers, exception handlers, and configuration parsers."
        }

        repo_chunks = []
        for mod, mod_chunks in by_module.items():
            files = list(dict.fromkeys([c.get("file") for c in mod_chunks if c.get("file")]))
            symbols = list(dict.fromkeys([c.get("name") for c in mod_chunks if c.get("name")]))
            desc = descriptions.get(mod.lower())
            if not desc:
                desc = f"Source code module for '{mod}', managing components such as: {', '.join(symbols[:8])} across files: {', '.join([os.path.basename(f) for f in files[:5]])}."

            repo_chunks.append({
                "chunk_id": f"repo:{mod}",
                "name": mod,
                "type": "RepositorySummary",
                "parent": None,
                "file": mod,
                "start_line": 1,
                "end_line": 1,
                "imports": [],
                "docstring": desc,
                "code": f"module {mod} contains files: " + " ".join(files[:20]),
                "chunk_index": 0,
                "total_chunks": 1,
                "level": 1,
                "level_name": "repo",
            })
        return repo_chunks

    def _make_file_chunk(
        self, file_path: str, file_chunks: List[Dict]
    ) -> Dict[str, Any]:
        """Create a synthetic file-level chunk by aggregating sub-chunk metadata."""
        names = [c.get("name", "") for c in file_chunks if c.get("name")]
        docstrings = [c.get("docstring", "") for c in file_chunks if c.get("docstring")]
        imports = []
        for c in file_chunks:
            imports.extend(c.get("imports", []))
        imports = list(dict.fromkeys(imports))

        return {
            "chunk_id": f"{file_path}:__file__",
            "name": file_path,
            "type": "FileSummary",
            "parent": None,
            "file": file_path,
            "start_line": 1,
            "end_line": file_chunks[-1].get("end_line", 0) if file_chunks else 0,
            "imports": imports[:30],
            "docstring": " | ".join(docstrings[:3]),
            "code": " ".join(names[:50]),  # symbol names as pseudo-code
            "chunk_index": 0,
            "total_chunks": 1,
            "level": 2,
            "level_name": "file",
        }

    def _build_search_text(self, chunk: Dict) -> str:
        return (
            f"SYMBOL:\n{chunk.get('name', '')}\n\n"
            f"TYPE:\n{chunk.get('type', '')}\n\n"
            f"FILE:\n{chunk.get('file', '')}\n\n"
            f"LEVEL:\n{chunk.get('level_name', '')}\n\n"
            f"DOCSTRING:\n{chunk.get('docstring', '')}\n\n"
            f"IMPORTS:\n{' '.join(chunk.get('imports', []))}\n\n"
            f"CODE:\n{chunk.get('code', '')}\n"
        )
