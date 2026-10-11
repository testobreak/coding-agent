# tests/test_context_aware_ranking.py

import unittest
from unittest.mock import MagicMock, patch

from retrieval.feature_extractor import RetrievalContext, RankingFeatures, FeatureExtractor
from retrieval.ranker import SpecRanker
from retrieval.retrieval_pipeline import RetrievalPipeline

class TestContextAwareRanking(unittest.TestCase):

    def test_ranking_features_extraction(self):
        # Setup context
        context = RetrievalContext(
            active_file="src/controllers/leave_controller.py",
            open_tabs=["src/controllers/leave_controller.py", "src/services/leave_service.py"],
            active_symbol="approve_leave",
            recent_files=["src/services/leave_service.py"],
            diagnostics=[
                MagicMock(file="src/controllers/leave_controller.py", message="SyntaxError")
            ],
            cursor_line=150
        )

        # Candidate 1: Matches active file, tab, symbol, diagnostics, and cursor proximity
        chunk1 = {
            "file": "src/controllers/leave_controller.py",
            "symbol": "approve_leave",
            "start_line": 155,
            "imports": ["src/services/leave_service.py"]
        }

        # Candidate 2: Inactive file (no matches)
        chunk2 = {
            "file": "src/utils/math_utils.py",
            "symbol": "add",
            "start_line": 10,
            "imports": []
        }

        features1 = FeatureExtractor.extract_features(chunk1, base_score=0.8, context=context)
        features2 = FeatureExtractor.extract_features(chunk2, base_score=0.8, context=context)

        # Assert features for chunk1
        self.assertEqual(features1.embedding_score, 0.8)
        self.assertGreater(features1.editor_score, 1.0) # 1.0 + cursor proximity boost
        self.assertEqual(features1.tab_score, 1.0)
        self.assertEqual(features1.symbol_score, 1.0)
        self.assertEqual(features1.diagnostics_score, 1.0)

        # Assert features for chunk2
        self.assertEqual(features2.embedding_score, 0.8)
        self.assertEqual(features2.editor_score, 0.0)
        self.assertEqual(features2.tab_score, 0.0)
        self.assertEqual(features2.symbol_score, 0.0)
        self.assertEqual(features2.diagnostics_score, 0.0)

    def test_composite_ranking_scores(self):
        # Case A: High semantic score, low metadata score
        features_a = RankingFeatures(
            embedding_score=0.9,
            editor_score=0.0,
            tab_score=0.0,
            import_score=0.0,
            symbol_score=0.0,
            recency_score=0.0,
            diagnostics_score=0.0
        )

        # Case B: Medium semantic score, high metadata score (active file + tab + symbol)
        features_b = RankingFeatures(
            embedding_score=0.6,
            editor_score=1.0,
            tab_score=1.0,
            import_score=0.5,
            symbol_score=0.8,
            recency_score=1.0,
            diagnostics_score=0.0
        )

        score_a = SpecRanker.rank(features_a)
        score_b = SpecRanker.rank(features_b)

        # Verify that SpecRanker ranks Case B higher than Case A because of multi-signal boost
        self.assertGreater(score_b, score_a)

    def test_pipeline_retrieve_and_rerank(self):
        # Mock retriever search
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            {"chunk": {"file": "src/utils/math_utils.py", "symbol": "add"}, "score": 0.9},
            {"chunk": {"file": "src/controllers/leave_controller.py", "symbol": "approve_leave"}, "score": 0.5}
        ]

        pipeline = RetrievalPipeline(retriever=mock_retriever)
        context = RetrievalContext(
            active_file="src/controllers/leave_controller.py",
            open_tabs=["src/controllers/leave_controller.py"],
            active_symbol="approve_leave"
        )

        # Run pipeline retrieve
        results = pipeline.retrieve(query="approve leave", context=context, top_k=2)

        # The controller chunk (score 0.5 originally) should rank 1st because of active file/tab/symbol boosts
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["chunk"]["symbol"], "approve_leave")
        self.assertEqual(results[1]["chunk"]["symbol"], "add")

if __name__ == "__main__":
    unittest.main()
