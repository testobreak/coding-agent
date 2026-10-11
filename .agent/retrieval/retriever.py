# retrieval/retriever.py

import os
import time
import threading
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from retrieval.embedding_engine import EmbeddingEngine
from retrieval.bm25_index import BM25Index
from retrieval.symbol_index import SymbolIndex
from retrieval.cross_encoder import CrossEncoderReranker
from retrieval.candidate_pipeline import CandidatePipeline
from retrieval.pgvector_backend import PgVectorBackend

if TYPE_CHECKING:
    from models.model_service import ModelService


class CodeRetriever:

    def __init__(
        self,
        repo_root=".",
        model_service: "ModelService" = None
    ):
        self.repo_root = repo_root
        self._index_ready = threading.Event()
        self._model_service = model_service  # kept for RepositoryService injection

        # Use injected ModelService — no model loading here
        self.embedding_engine = EmbeddingEngine(model_service=model_service)

        self.chunks = []
        self.bm25_index = BM25Index()
        self.symbol_index = SymbolIndex()

        # Cross-encoder: injected via service (lazy — no startup cost)
        self.cross_encoder = CrossEncoderReranker(model_service=model_service)
        
        # Initialize pgvector HNSW ANN backend
        self.pgvector_backend = PgVectorBackend()
        
        self.candidate_pipeline = CandidatePipeline(
            ann_backend=self.pgvector_backend,
            bm25_index=self.bm25_index,
            symbol_index=self.symbol_index,
            cross_encoder=self.cross_encoder
        )

        print("\n[Retriever] Initializing")
        self.get_project_metadata()

        # Launch indexing in background so startup is non-blocking
        index_thread = threading.Thread(
            target=self._background_index,
            name="retriever-indexer",
            daemon=True
        )
        index_thread.start()

    def get_project_metadata(self):
        import json
        from pathlib import Path
        root = Path(self.repo_root)
        self.metadata_path = root / ".agent" / "project_metadata.json"
        self.project_type = None
        self.project_units = []

        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.project_type = data.get("project_type")
                    from execution.project_classifier import ProjectType, ProjectUnit
                    self.project_units = [
                        ProjectUnit(root=u["root"], type=ProjectType(u["type"]))
                        for u in data.get("project_units", [])
                    ]
            except Exception:
                pass
                
        if not self.project_type:
            from execution.project_classifier import ProjectClassifier
            classifier = ProjectClassifier()
            units = classifier.detect_subprojects(root)
            self.project_units = units
            
            if not units:
                self.project_type = "unknown"
            elif len(units) > 1:
                self.project_type = "monorepo"
            else:
                self.project_type = units[0].type.value
                
            try:
                self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.metadata_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "project_type": self.project_type,
                        "project_units": [{"root": u.root, "type": u.type.value} for u in self.project_units]
                    }, f, indent=2)
            except Exception:
                pass

    def _background_index(self):
        """Run in a daemon thread: skip full scan if already indexed, else run incremental."""
        try:
            from repository_intelligence.db.connection import SessionLocal
            from repository_intelligence.models.symbol import Symbol
            from repository_intelligence.models.file import File

            session = SessionLocal()
            try:
                existing_count = session.query(Symbol).count()
            finally:
                session.close()

            if existing_count > 0:
                # Already indexed — just load chunks from DB into memory
                print(f"[Retriever] DB has {existing_count} symbols — skipping full scan, loading from DB...")
                self._load_chunks_from_db()
                self._index_ready.set()
                # Run incremental scan silently in background to catch any changes
                self._incremental_scan_background()
            else:
                # First run — must do full index
                self.build_index()
                self._index_ready.set()
        except Exception as e:
            print(f"[Retriever] Background indexing error: {e}")
            self._index_ready.set()  # unblock searches even if indexing failed

    def _incremental_scan_background(self):
        """Silently run incremental scan to pick up any changed files."""
        try:
            from repository_intelligence.services.repository_service import RepositoryService
            RepositoryService(model_service=self._model_service).scan_repository(self.repo_root)
            # Reload chunks after incremental update
            self._load_chunks_from_db()
            print("[Retriever] Background incremental scan complete.")
        except Exception as e:
            print(f"[Retriever] Background incremental scan warning: {e}")

    def _load_chunks_from_db(self):
        """Load symbol chunks from DB into memory for BM25 and symbol index."""
        from repository_intelligence.db.connection import SessionLocal
        from repository_intelligence.models.symbol import Symbol
        from repository_intelligence.models.file import File
        from retrieval.corpus_filter import is_corpus_eligible

        session = SessionLocal()
        skipped = 0
        try:
            db_symbols = session.query(Symbol).join(File, Symbol.file_id == File.id).all()
            self.chunks = []
            for sym in db_symbols:
                file_path = sym.file.path if sym.file else ""

                # ── Corpus hygiene guard ────────────────────────────────────
                # Reject build artifacts, agent internals, generated files, etc.
                if not is_corpus_eligible(file_path):
                    skipped += 1
                    continue

                self.chunks.append({
                    "chunk_id": f"db:symbol:{sym.id}",
                    "name": sym.name,
                    "symbol": sym.qualified_name,
                    "type": sym.symbol_type or "ClassDef",
                    "file": file_path,
                    "start_line": sym.start_line,
                    "end_line": sym.end_line,
                    "code": sym.signature or "",
                    "docstring": ""
                })
            self.bm25_index.build(self.chunks)
            self.symbol_index.build(self.chunks)
            print(
                f"[Retriever] Loaded {len(self.chunks)} chunks from DB "
                f"({skipped} ineligible paths skipped)."
            )
        finally:
            session.close()


    # =====================================================
    # INDEX BUILD
    # =====================================================

    def build_index(self):
        start = time.time()
        print("[Retriever] Scanning and indexing repository to PostgreSQL...")

        # Stage 1: Incremental repository scan + embedding
        t0 = time.time()
        from repository_intelligence.services.repository_service import RepositoryService
        try:
            result = RepositoryService(model_service=self._model_service).scan_repository(self.repo_root)
            changed = result.get("changed_files", 0)
            scanned = result.get("scanned_files", 0)
            print(f"[Retriever] Scan complete: {scanned} scanned, {changed} changed files ({time.time() - t0:.2f}s)")
        except Exception as e:
            print(f"[Retriever Error] Database indexing scan failed: {e}")
            raise e

        # Stage 2: Load chunks into memory (BM25 + symbol index)
        t1 = time.time()
        self._load_chunks_from_db()
        print(f"[Retriever] In-memory index built in {time.time() - t1:.2f}s")

        print(f"[Retriever] Indexed {len(self.chunks)} chunks in {time.time() - start:.2f}s total")

    # =====================================================
    # SEARCH
    # =====================================================

    def search(
        self,
        query,
        top_k=10
    ):
        """
        Graph-first search — the primary entry point for all retrieval.

        Routing order (never run ANN until structural resolution fails):
          1. SYMBOL route  — known symbol in graph cache → 0 ms, no ANN
          2. GRAPH route   — structural question (callers/deps/impls) → 1-5 ms, no ANN
          3. SEMANTIC route — fuzzy/conceptual query → ANN + BM25 + CandidatePipeline
        """
        start = time.time()

        # ── Stage 1: Structural resolution ──────────────────────────────────
        from retrieval.query_resolver import QueryResolver
        from retrieval.query_intent import ResolutionMode

        try:
            resolver = QueryResolver()
            plan = resolver.resolve(query, self.repo_root)

            # ── SYMBOL route ────────────────────────────────────────────────
            if plan.mode == ResolutionMode.SYMBOL and plan.symbols:
                results = self._resolve_symbol_path(plan, top_k)
                elapsed = time.time() - start
                print(
                    f"[Retriever] Resolution: SYMBOL ({', '.join(plan.symbol_names[:3])}) "
                    f"— {elapsed * 1000:.1f}ms, skipped ANN"
                )
                if results:
                    return results
                # Partial match — symbol found but no file. Cascade to SEMANTIC.
                print("[Retriever] SYMBOL route yielded no chunks — cascading to SEMANTIC")

            # ── GRAPH route ─────────────────────────────────────────────────
            elif plan.mode == ResolutionMode.GRAPH:
                from retrieval.graph_resolver import GraphResolver
                graph_results = GraphResolver().resolve(plan, top_k)
                elapsed = time.time() - start
                print(
                    f"[Retriever] Resolution: GRAPH (op={plan.graph_op}, "
                    f"symbols={len(plan.symbols)}) — {elapsed * 1000:.1f}ms, skipped ANN"
                )
                if graph_results:
                    # Wrap in standard {score, chunk} format
                    return [{"score": c.pop("score", 0.90), "chunk": c} for c in graph_results]
                # Graph returned nothing — cascade to SEMANTIC
                print("[Retriever] GRAPH route yielded no chunks — cascading to SEMANTIC")

            else:
                elapsed = time.time() - start
                print(
                    f"[Retriever] Resolution: SEMANTIC ({query[:60]}) "
                    f"— ANN triggered after {elapsed * 1000:.1f}ms classifier"
                )

        except Exception as e:
            print(f"[Retriever] QueryResolver error (falling back to SEMANTIC): {e}")

        # ── Stage 2: Semantic fallback — ANN + BM25 + CandidatePipeline ────
        return self._semantic_search(query, top_k, start)

    def _resolve_symbol_path(self, plan, top_k: int):
        """
        SYMBOL route: read actual source spans from the graph cache and wrap
        them in chunk-compatible dicts with score=1.0 (deterministic).
        """
        from retrieval.graph_resolver import GraphResolver
        gr = GraphResolver()

        chunks = []
        seen = set()
        for sym in plan.symbols[:top_k]:
            sym_id = sym.get("id")
            if sym_id in seen:
                continue
            seen.add(sym_id)
            chunk = gr._sym_to_chunk(sym, score=1.0)
            if chunk:
                chunks.append({"score": chunk.pop("score", 1.0), "chunk": chunk})

        return chunks

    def _semantic_search(self, query: str, top_k: int, start: float = None):
        """
        SEMANTIC fallback — ANN embedding + pgvector + BM25 + CandidatePipeline.
        Only reached when structural resolution fails or returns empty.
        """
        if start is None:
            import time as _time
            start = _time.time()

        from retrieval.query_intent import RetrievalIntentClassifier
        intent = RetrievalIntentClassifier.classify(query)

        if self.candidate_pipeline:
            embedding = self.embedding_engine.embed_text(query)
            results = self.candidate_pipeline.retrieve(
                query=query,
                query_embedding=embedding,
                top_k=top_k,
                intent=intent.value
            )
        else:
            embedding = self.embedding_engine.embed_text(query)
            results = self.pgvector_backend.search(embedding, k=top_k)

        elapsed = time.time() - start
        print(f"[Retriever] SEMANTIC search completed in {elapsed * 1000:.1f}ms")
        return results
