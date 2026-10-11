# retrieval/embedding_engine.py
#
# EmbeddingEngine wraps a shared SentenceTransformer model provided by ModelService.
# DO NOT instantiate SentenceTransformer directly here.

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.model_service import ModelService


class EmbeddingEngine:
    """
    Thin inference wrapper around a shared embedding model.

    The model instance is owned by ModelService and injected here.
    This class does NOT load any model weights itself.

    Parameters
    ----------
    model_service : ModelService
        The central model service. If None, falls back to legacy
        self-loading for backwards compatibility during transition.
    """

    def __init__(self, model_service: "ModelService" = None):
        if model_service is not None:
            self._model_service = model_service
            self._model = None          # resolved lazily via service
        else:
            # Legacy fallback: load model directly.
            # This path should only be hit during transition.
            # Remove once all callers are migrated.
            import time
            from sentence_transformers import SentenceTransformer
            print("[EmbeddingEngine] WARNING: No ModelService provided, loading model directly (legacy path).")
            t0 = time.time()
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._model_service = None
            print(f"[EmbeddingEngine] Model loaded in {time.time() - t0:.2f}s")

    @property
    def model(self):
        if self._model_service is not None:
            return self._model_service.get_embedding_model()
        return self._model

    def embed_text(self, text: str) -> "np.ndarray":
        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embedding.astype(np.float32)

    def embed_batch(self, texts, batch_size: int = 32) -> "np.ndarray":
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True
        )
        return embeddings.astype(np.float32)
