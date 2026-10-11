# tests/test_hierarchical_retrieval.py

import unittest
from unittest.mock import MagicMock, patch
import os
import numpy as np

from retrieval.hierarchy.hierarchical_index import HierarchicalIndex
from retrieval.hierarchy.hierarchical_retriever import HierarchicalRetriever
from retrieval.hierarchy.hierarchical_store import HierarchicalStore
from retrieval.embedding_engine import EmbeddingEngine

class TestHierarchicalRetrieval(unittest.TestCase):

    def setUp(self):
        # Create mock chunks
        self.chunks = [
            # Auth module
            {
                "chunk_id": "auth_1",
                "name": "login",
                "type": "FunctionDef",
                "file": "auth/service.py",
                "docstring": "Authenticates a user.",
                "code": "def login(): pass",
                "imports": ["hashlib"]
            },
            {
                "chunk_id": "auth_2",
                "name": "UserSession",
                "type": "ClassDef",
                "file": "auth/models.py",
                "docstring": "User session model.",
                "code": "class UserSession: pass",
                "imports": []
            },
            # Payroll module
            {
                "chunk_id": "pay_1",
                "name": "calculate_salary",
                "type": "FunctionDef",
                "file": "payroll/calculator.py",
                "docstring": "Calculates net salary.",
                "code": "def calculate_salary(): pass",
                "imports": ["math"]
            },
            # Generic chunk (Level 4)
            {
                "chunk_id": "gen_1",
                "name": "helper",
                "type": "Expression",
                "file": "core/utils.py",
                "docstring": "Utility helper function.",
                "code": "x = 10",
                "imports": []
            }
        ]

        # Mock embedding engine to return dummy normalized embeddings
        self.mock_engine = MagicMock(spec=EmbeddingEngine)
        
        def mock_embed_text(text):
            # Deterministic dummy embedding (384 dimensions)
            emb = np.zeros(384, dtype=np.float32)
            # Make payroll queries match payroll module index
            if "salary" in text.lower() or "calculator" in text.lower():
                emb[0] = 1.0
            elif "login" in text.lower() or "auth" in text.lower():
                emb[1] = 1.0
            else:
                emb[2] = 1.0
            return emb

        def mock_embed_batch(texts):
            embs = []
            for t in texts:
                embs.append(mock_embed_text(t))
            return np.array(embs)

        self.mock_engine.embed_text.side_effect = mock_embed_text
        self.mock_engine.embed_batch.side_effect = mock_embed_batch

    def test_hierarchical_index_build(self):
        idx = HierarchicalIndex(self.mock_engine)
        idx.build(self.chunks)

        self.assertIsNotNone(idx.store)
        sizes = idx.store.sizes()
        
        # Verify Level 1: Repository summaries (should contain auth, payroll, core)
        self.assertEqual(sizes["L1_repo"], 3)
        
        # Verify Level 2: File summaries (auth/service.py, auth/models.py, payroll/calculator.py, core/utils.py)
        self.assertEqual(sizes["L2_file"], 4)
        
        # Verify Level 3: Symbols (login, UserSession, calculate_salary)
        self.assertEqual(sizes["L3_symbol"], 3)
        
        # Verify Level 4: Chunks (generic helper)
        self.assertEqual(sizes["L4_chunk"], 1)

    def test_cascading_search(self):
        idx = HierarchicalIndex(self.mock_engine)
        idx.build(self.chunks)

        retriever = HierarchicalRetriever(idx.store, self.mock_engine)
        
        # Search for salary (should filter down to payroll module and files)
        results = retriever.search("salary query", top_k=5)
        self.assertTrue(len(results) > 0)
        
        # Top result should contain payroll chunks or files
        top_chunk = results[0]["chunk"]
        self.assertTrue(
            "payroll" in top_chunk["file"] or top_chunk["name"] == "payroll"
        )

        # Search for login (should filter to auth module and files)
        results_auth = retriever.search("login query", top_k=5)
        self.assertTrue(len(results_auth) > 0)
        top_auth_chunk = results_auth[0]["chunk"]
        self.assertTrue(
            "auth" in top_auth_chunk["file"] or top_auth_chunk["name"] == "auth"
        )

if __name__ == "__main__":
    unittest.main()
