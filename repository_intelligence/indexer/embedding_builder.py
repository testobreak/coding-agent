# repository_intelligence/indexer/embedding_builder.py
#
# EmbeddingBuilder wraps a shared SentenceTransformer model provided by ModelService.
# DO NOT call SentenceTransformer() directly here.

import hashlib
import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.model_service import ModelService


class EmbeddingBuilder:

    model_name = "all-MiniLM-L6-v2"
    dimensions = 384

    def __init__(self, model_service: "ModelService" = None):
        self._model_service = model_service
        self._model = None          # legacy fallback cache

    @property
    def model(self):
        """Return the shared model from ModelService, or lazy-load as fallback."""
        if self._model_service is not None:
            return self._model_service.get_embedding_model()

        # Legacy path — only hit if no ModelService was injected
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            print("[EmbeddingBuilder] WARNING: No ModelService provided, loading model directly (legacy path).")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def build(self, text: str) -> list[float]:
        try:
            emb = self.model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            return [float(x) for x in emb]
        except Exception as e:
            print(f"[EmbeddingBuilder] Error generating semantic embeddings: {e}. Falling back to token hashing.")
            return self._fallback_build(text)

    def content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _fallback_build(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions

        for token in self._tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self.dimensions
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))

        if not norm:
            return vector

        return [round(value / norm, 6) for value in vector]

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())
