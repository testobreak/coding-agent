"""Cross-encoder reranker for code retrieval results.

Delegates model loading to ModelService (dependency injection).
Does NOT instantiate CrossEncoder directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from models.model_service import ModelService

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Reranks code-retrieval candidates using a cross-encoder model.

    Parameters
    ----------
    model_service : ModelService, optional
        Central model service. If provided, model is obtained via
        get_cross_encoder() (lazy, no startup cost).
        If None, falls back to the legacy self-loading path.
    model_name : str
        HuggingFace model identifier (used only for legacy fallback).

    Attributes
    ----------
    available : bool
        ``True`` when the underlying model was loaded successfully.
    """

    def __init__(
        self,
        model_service: Optional["ModelService"] = None,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ) -> None:
        self.model_name = model_name
        self._model_service = model_service
        self._legacy_model = None
        self._legacy_available = False

        # If no service provided, lazy-load on first rerank call (legacy path)
        # No model load in __init__ — cross-encoder must NOT affect startup time

    @property
    def model(self):
        """Return model from ModelService, or legacy self-loaded model."""
        if self._model_service is not None:
            return self._model_service.get_cross_encoder()
        # Legacy: load once on first access
        if self._legacy_model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._legacy_model = CrossEncoder(self.model_name)
                self._legacy_available = True
                logger.info("CrossEncoder '%s' loaded (legacy path).", self.model_name)
            except Exception:
                logger.exception("CrossEncoder load failed (legacy path).")
        return self._legacy_model

    @property
    def available(self) -> bool:
        if self._model_service is not None:
            return self._model_service.get_cross_encoder() is not None
        return self._legacy_available

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @classmethod
    def is_available(cls) -> bool:
        """Return ``True`` if ``sentence_transformers`` can be imported."""
        try:
            import sentence_transformers  # noqa: F401, type: ignore[import-untyped]

            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def rerank(
        self,
        query: str,
        candidates: List[Dict],
        k: int = 20,
    ) -> List[Dict]:
        """Rescore *candidates* against *query* and return the top-*k*.

        Each candidate must follow the schema::

            {"score": float, "chunk": dict}

        where ``chunk`` may contain the keys ``symbol``, ``file``, ``code``
        (or ``content``).

        When the cross-encoder model is unavailable the method falls back to
        returning the candidates sorted by their original ``score`` field,
        truncated to *k* items.

        Parameters
        ----------
        query : str
            The user/search query string.
        candidates : list[dict]
            Retrieval results, each carrying a ``score`` and a ``chunk``.
        k : int
            Maximum number of results to return (default ``20``).

        Returns
        -------
        list[dict]
            Top-*k* candidates sorted by cross-encoder score (descending).
        """
        if not candidates:
            return []

        # ---- Fallback path ------------------------------------------------
        if not self.available or self.model is None:
            return sorted(
                candidates,
                key=lambda c: c.get("score", 0.0),
                reverse=True,
            )[:k]

        # ---- Build query–document pairs -----------------------------------
        pairs: List[List[str]] = []
        for candidate in candidates:
            chunk = candidate.get("chunk", {})
            chunk_text = self._build_chunk_text(chunk)
            pairs.append([query, chunk_text])

        # ---- Score with cross-encoder -------------------------------------
        try:
            scores = self.model.predict(pairs)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Cross-encoder inference failed; returning candidates "
                "sorted by original score."
            )
            return sorted(
                candidates,
                key=lambda c: c.get("score", 0.0),
                reverse=True,
            )[:k]

        # ---- Attach new scores and sort -----------------------------------
        reranked: List[Dict] = []
        for candidate, new_score in zip(candidates, scores):
            copied = dict(candidate)
            copied["score"] = float(new_score)
            reranked.append(copied)

        reranked.sort(key=lambda c: c["score"], reverse=True)
        return reranked[:k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_chunk_text(chunk: Dict) -> str:
        """Construct the document string fed to the cross-encoder.

        Format::

            <symbol> | <file>
            <first 512 chars of code/content>
        """
        symbol = chunk.get("symbol", "")
        file_path = chunk.get("file", "")
        code = chunk.get("code", chunk.get("content", ""))[:512]
        return f"{symbol} | {file_path}\n{code}"
