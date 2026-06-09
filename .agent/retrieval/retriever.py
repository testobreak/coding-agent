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

from retrieval.vector_store import (
    VectorStore
)


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

    # =====================================================
    # CACHE
    # =====================================================

    def cache_exists(self):

        return (

            os.path.exists(INDEX_FILE)

            and

            os.path.exists(CHUNKS_FILE)
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
            VectorStore(dimension)
        )

        for embedding, chunk in zip(
            embeddings,
            self.chunks
        ):

            self.vector_store.add(
                embedding,
                chunk
            )

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

        faiss.write_index(
            self.vector_store.index,
            INDEX_FILE
        )

        with open(
            CHUNKS_FILE,
            "wb"
        ) as f:

            pickle.dump(
                self.chunks,
                f
            )

        print(
            "[Retriever] Cache saved"
        )

    # =====================================================
    # LOAD CACHE
    # =====================================================

    def load_cache(self):

        index = faiss.read_index(
            INDEX_FILE
        )

        with open(
            CHUNKS_FILE,
            "rb"
        ) as f:

            chunks = pickle.load(f)

        dimension = index.d

        self.vector_store = (
            VectorStore(dimension)
        )

        self.vector_store.index = index

        self.vector_store.chunks = chunks

        self.chunks = chunks

        print(
            f"[Retriever] "
            f"Loaded {len(chunks)} chunks"
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

        embedding = (
            self.embedding_engine
            .embed_text(query)
        )

        results = (
            self.vector_store.search(
                embedding,
                top_k=top_k
            )
        )

        end = time.time()

        print(
            f"[Retriever] Search took "
            f"{end - start:.2f}s"
        )

        return results
