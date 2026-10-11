# models/model_service.py
#
# Central model ownership for Local Cursor.
# Only this module may instantiate SentenceTransformer or CrossEncoder.
# All consumers receive models via dependency injection.

from __future__ import annotations

import threading
import time
from typing import Optional


class ModelConfig:
    """Holds model name configuration — override via environment variables."""

    embedding_model: str = "all-MiniLM-L6-v2"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    embedding_dimensions: int = 384


class ModelService:
    """
    Centralized model lifecycle manager for Local Cursor.

    Rules:
    - Only this class may call SentenceTransformer(...) or CrossEncoder(...)
    - Consumers (Retriever, EmbeddingEngine, EmbeddingBuilder, HybridRanker)
      receive the model via get_embedding_model() / get_cross_encoder()
    - Embedding model is always-hot (eager preload on first access)
    - Cross-encoder is lazy — loaded only on first reranking call
    - Thread-safe: two concurrent calls to get_embedding_model() will
      only ever produce one model instance
    """

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()

        self._embedding_model = None
        self._cross_encoder = None

        self._embedding_lock = threading.Lock()
        self._cross_encoder_lock = threading.Lock()

        self._embedding_load_time: Optional[float] = None
        self._cross_encoder_load_time: Optional[float] = None

    # ------------------------------------------------------------------
    # Embedding model  (always hot)
    # ------------------------------------------------------------------

    def get_embedding_model(self):
        """
        Return the shared SentenceTransformer instance.
        Loads on first call; subsequent calls return the cached instance.
        Thread-safe double-checked locking.
        """
        if self._embedding_model is not None:
            return self._embedding_model

        with self._embedding_lock:
            if self._embedding_model is None:
                self._embedding_model = self._load_embedding_model()

        return self._embedding_model

    def _load_embedding_model(self):
        from sentence_transformers import SentenceTransformer
        model_name = self.config.embedding_model
        print(f"[ModelService] Loading embedding model '{model_name}'...")
        t0 = time.time()
        model = SentenceTransformer(model_name)
        elapsed = time.time() - t0
        self._embedding_load_time = elapsed
        print(f"[ModelService] Embedding model loaded in {elapsed:.2f}s")
        return model

    # ------------------------------------------------------------------
    # Cross-encoder  (lazy — only on first rerank call)
    # ------------------------------------------------------------------

    def get_cross_encoder(self):
        """
        Return the shared CrossEncoder instance.
        Does NOT load during startup — lazy on first use.
        Returns None if sentence-transformers is not installed.
        """
        if self._cross_encoder is not None:
            return self._cross_encoder

        with self._cross_encoder_lock:
            if self._cross_encoder is None:
                self._cross_encoder = self._load_cross_encoder()

        return self._cross_encoder

    def _load_cross_encoder(self):
        try:
            from sentence_transformers import CrossEncoder
            model_name = self.config.cross_encoder_model
            print(f"[ModelService] Lazy-loading cross-encoder '{model_name}'...")
            t0 = time.time()
            model = CrossEncoder(model_name)
            elapsed = time.time() - t0
            self._cross_encoder_load_time = elapsed
            print(f"[ModelService] Cross-encoder loaded in {elapsed:.2f}s")
            return model
        except ImportError:
            print("[ModelService] sentence-transformers not installed; cross-encoder disabled.")
            return None
        except Exception as e:
            print(f"[ModelService] Cross-encoder load failed: {e}; falling back to score sort.")
            return None

    # ------------------------------------------------------------------
    # Warm startup helper
    # ------------------------------------------------------------------

    def preload(self):
        """
        Eagerly load only the embedding model.
        Call once at startup to avoid cold-path latency on first query.
        Does NOT load the cross-encoder (keep it lazy).
        """
        self.get_embedding_model()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def status(self) -> dict:
        return {
            "embedding_model": self.config.embedding_model,
            "embedding_loaded": self._embedding_model is not None,
            "embedding_load_time_s": self._embedding_load_time,
            "cross_encoder_model": self.config.cross_encoder_model,
            "cross_encoder_loaded": self._cross_encoder is not None,
            "cross_encoder_load_time_s": self._cross_encoder_load_time,
        }
