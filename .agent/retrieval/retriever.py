# retrieval/retriever.py

import os
import time
import pickle
import faiss

from retrieval.chunker import (
    RepoChunker
)

from retrieval.embedding_engine import (
    EmbeddingEngine
)

from retrieval.hierarchy.hierarchical_index import (
    HierarchicalIndex
)

from retrieval.faiss_store import (
    FaissVectorStore
)

from retrieval.bm25_index import BM25Index
from retrieval.symbol_index import SymbolIndex
from retrieval.cross_encoder import CrossEncoderReranker
from retrieval.candidate_pipeline import CandidatePipeline


INDEX_DIR = ".cache"

INDEX_FILE = os.path.join(
    INDEX_DIR,
    "code_index.faiss"
)

CHUNKS_FILE = os.path.join(
    INDEX_DIR,
    "chunks.pkl"
)


class CodeRetriever:

    def __init__(
        self,
        repo_root="."
    ):

        self.repo_root = repo_root

        os.makedirs(
            INDEX_DIR,
            exist_ok=True
        )

        self.chunker = RepoChunker()

        self.embedding_engine = (
            EmbeddingEngine()
        )

        self.chunks = []

        self.vector_store = None
        self.bm25_index = BM25Index()
        self.symbol_index = SymbolIndex()
        self.cross_encoder = CrossEncoderReranker()
        self.candidate_pipeline = None

        self.hierarchical_index = HierarchicalIndex(self.embedding_engine)

        print(
            "\n[Retriever] Initializing"
        )

        if self.cache_exists():

            try:

                self.load_cache()

            except Exception as e:

                print(
                    f"[Retriever] "
                    f"Cache load failed: {e}"
                )

                self.build_index()

        else:

            self.build_index()

        self.get_project_metadata()

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

    # =====================================================
    # CACHE
    # =====================================================

    def cache_exists(self):
        return (
            os.path.exists(".cache/vector_store.index")
            and
            os.path.exists(".cache/vector_store.meta")
            and
            os.path.exists(".cache/hier_level_1.faiss")
        )

    # =====================================================
    # INDEX BUILD
    # =====================================================

    def build_index(self):

        start = time.time()

        print(
            "[Retriever] Building chunks"
        )

        self.chunks = (
            self.chunker.build_chunks(
                self.repo_root
            )
        )

        if not self.chunks:

            raise RuntimeError(
                "No chunks generated."
            )

        texts = [

            self.build_search_text(chunk)

            for chunk in self.chunks
        ]

        print(
            "[Retriever] Embedding chunks"
        )

        embeddings = (
            self.embedding_engine
            .embed_batch(texts)
        )

        dimension = embeddings.shape[1]

        self.vector_store = (
            FaissVectorStore(dimension)
        )

        chunk_ids = [c.get("chunk_id", str(i)) for i, c in enumerate(self.chunks)]
        self.vector_store.add_embeddings(
            chunk_ids,
            embeddings.tolist(),
            self.chunks
        )

        # Build BM25 and Symbol indexes
        self.bm25_index.build(self.chunks)
        self.symbol_index.build(self.chunks)

        # Build CandidatePipeline
        self.candidate_pipeline = CandidatePipeline(
            vector_store=self.vector_store,
            bm25_index=self.bm25_index,
            symbol_index=self.symbol_index,
            cross_encoder=self.cross_encoder
        )

        # Build and save hierarchical index
        self.hierarchical_index = HierarchicalIndex(self.embedding_engine)
        self.hierarchical_index.build(self.chunks)
        self.hierarchical_index.save()

        self.save_cache()

        end = time.time()

        print(
            f"[Retriever] "
            f"Indexed {len(self.chunks)} "
            f"chunks in "
            f"{end - start:.2f}s"
        )

    # =====================================================
    # SEARCH TEXT
    # =====================================================

    def build_search_text(
        self,
        chunk
    ):

        return f"""
SYMBOL:
{chunk.get("name", "")}

TYPE:
{chunk.get("type", "")}

FILE:
{chunk.get("file", "")}

DOCSTRING:
{chunk.get("docstring", "")}

IMPORTS:
{' '.join(chunk.get("imports", []))}

CODE:
{chunk.get("code", "")}
"""

    # =====================================================
    # SAVE CACHE
    # =====================================================

    def save_cache(self):
        self.vector_store.save(os.path.join(INDEX_DIR, "vector_store"))
        print(
            "[Retriever] Cache saved"
        )

    # =====================================================
    # LOAD CACHE
    # =====================================================

    def load_cache(self):
        self.vector_store = FaissVectorStore(384)
        self.vector_store.load(os.path.join(INDEX_DIR, "vector_store"))
        
        self.chunks = list(self.vector_store.chunks_map.values())

        # Rebuild BM25 and Symbol indexes from cached chunks
        self.bm25_index.build(self.chunks)
        self.symbol_index.build(self.chunks)

        # Build CandidatePipeline
        self.candidate_pipeline = CandidatePipeline(
            vector_store=self.vector_store,
            bm25_index=self.bm25_index,
            symbol_index=self.symbol_index,
            cross_encoder=self.cross_encoder
        )

        # Load hierarchical index
        self.hierarchical_index = HierarchicalIndex(self.embedding_engine)
        if self.hierarchical_index.cache_exists():
            self.hierarchical_index.load()
        else:
            self.hierarchical_index.build(self.chunks)
            self.hierarchical_index.save()

        print(
            f"[Retriever] "
            f"Loaded {len(self.chunks)} chunks"
        )

    # =====================================================
    # SEARCH
    # =====================================================

    def search(
        self,
        query,
        top_k=10
    ):
        start = time.time()

        # 1. Resolve query targets using QueryResolver
        from retrieval.query_resolver import QueryResolver
        from repository_intelligence.db.connection import SessionLocal
        
        db_session = SessionLocal()
        try:
            resolver = QueryResolver(db_session)
            resolved = resolver.resolve(query, self.repo_root)
            
            # If we resolved specific target files, perform directed retrieval on graph neighborhood
            if resolved.target_files:
                print(f"[Retriever] Directed retrieval triggered for files: {resolved.target_files}")
                target_file_paths = set(resolved.target_files)
                
                from repository_intelligence.models.symbol import Symbol, SymbolRelationship
                from repository_intelligence.models.file import File
                
                sym_rows = db_session.query(Symbol.id).join(File, Symbol.file_id == File.id).filter(
                    File.path.in_(list(target_file_paths))
                ).all()
                sym_ids = [r[0] for r in sym_rows]
                
                if sym_ids:
                    # Find 1st degree neighbor symbol files in graph
                    neighbors = db_session.query(File.path).join(
                        Symbol, Symbol.file_id == File.id
                    ).join(
                        SymbolRelationship, 
                        (SymbolRelationship.target_symbol_id == Symbol.id) | 
                        (SymbolRelationship.source_symbol_id == Symbol.id)
                    ).filter(
                        (SymbolRelationship.source_symbol_id.in_(sym_ids)) |
                        (SymbolRelationship.target_symbol_id.in_(sym_ids))
                    ).all()
                    
                    for r in neighbors:
                        if r[0]:
                            target_file_paths.add(r[0])
                            
                directed_chunks = [c for c in self.chunks if c.get("file") in target_file_paths]
                
                if directed_chunks:
                    print(f"[Retriever] Directed search space restricted to {len(directed_chunks)} chunks in {len(target_file_paths)} files.")
                    results = []
                    for c in directed_chunks:
                        score = 0.50
                        if c.get("file") in resolved.target_files:
                            score = 1.0
                        results.append({"score": score, "chunk": c})
                        
                    from retrieval.hybrid_ranker import HybridRanker
                    ranker = HybridRanker()
                    ranked = ranker.rank(query, results, session=db_session)
                    end = time.time()
                    print(f"[Retriever] Directed search took {end - start:.2f}s")
                    return ranked[:top_k]
        except Exception as e:
            print(f"[Retriever] Directed search fallback failed: {e}")
        finally:
            db_session.close()

        # 2. Fallback to two-stage CandidatePipeline (ANN + BM25 + Symbol → Rerank)
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
        elif self.hierarchical_index and self.hierarchical_index.store:
            from retrieval.hierarchy.hierarchical_retriever import HierarchicalRetriever
            retriever = HierarchicalRetriever(
                store=self.hierarchical_index.store,
                embedding_engine=self.embedding_engine
            )
            results = retriever.search(query, top_k=top_k)
        else:
            embedding = self.embedding_engine.embed_text(query)
            results = self.vector_store.search(embedding, k=top_k)

        end = time.time()
        print(f"[Retriever] Fallback search took {end - start:.2f}s")
        return results
