# retrieval/ranker.py
#
# Multi-signal ranking engine.

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from retrieval.feature_extractor import RankingFeatures, FeatureExtractor, RetrievalContext

class SpecRanker:
    """
    SpecRanker combining semantic, structural, and local editor signals.
    """
    @staticmethod
    def rank(features: RankingFeatures) -> float:
        """
        Computes final ranking score by combining individual weights.
        """
        score = (
            0.30 * features.embedding_score +
            0.20 * features.editor_score +
            0.10 * features.tab_score +
            0.15 * features.import_score +
            0.20 * features.symbol_score +
            0.05 * features.recency_score
        )
        
        # Add diagnostics boost to elevate files currently reporting errors
        if features.diagnostics_score > 0.0:
            score += 0.15 * features.diagnostics_score
            
        return score

    @classmethod
    def rerank_candidates(
        cls,
        candidates: List[Dict[str, Any]],
        context: Optional[RetrievalContext] = None,
        db_session = None
    ) -> List[Dict[str, Any]]:
        """
        Enriches candidate chunks with features and reranks them.
        """
        reranked = []
        for item in candidates:
            # Handle both dictionary and direct chunk object inputs
            chunk = item.get("chunk", item) if isinstance(item, dict) else item
            base_score = item.get("score", 0.0) if isinstance(item, dict) else 0.0
            
            features = FeatureExtractor.extract_features(
                chunk=chunk,
                base_score=base_score,
                context=context,
                db_session=db_session
            )
            final_score = cls.rank(features)
            
            reranked.append({
                "chunk": chunk,
                "score": final_score,
                "features": features
            })
            
        reranked.sort(key=lambda x: x["score"], reverse=True)
        return reranked
