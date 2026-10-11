# tests/test_context_caching.py

import unittest
from unittest.mock import MagicMock, patch
import os

from context.cache import ContextCache, CachedContext
from context.context_builder import ContextBuilder, ContextRadius
from context.context_package import ContextPackage

class TestContextCaching(unittest.TestCase):

    def setUp(self):
        ContextCache.clear()

    def tearDown(self):
        ContextCache.clear()

    def test_touched_files_hash(self):
        # Test that touched files hash is consistent for the same inputs
        hash1 = ContextCache.get_touched_files_hash(repo_root=os.getcwd(), active_file="test_file.py")
        hash2 = ContextCache.get_touched_files_hash(repo_root=os.getcwd(), active_file="test_file.py")
        self.assertEqual(hash1, hash2)

        # Test that different active files give different hashes (or different mtimes)
        hash3 = ContextCache.get_touched_files_hash(repo_root=os.getcwd(), active_file="other_file.py")
        self.assertNotEqual(hash1, hash3)

    def test_cache_set_and_get(self):
        task_id = "test-task-123"
        active_file = "app/main.py"
        symbol_ctx = ContextPackage(goal="optimize function", primary_symbol=None, previous_attempts=[])
        assembled_prompt = "System Prompt + Code Context + Goal"
        tokenized_prompt = [1, 2, 3, 4]

        # Verify initial get returns None
        cached = ContextCache.get(task_id, active_file)
        self.assertNil = self.assertIsNone(cached)

        # Set value
        ContextCache.set(
            task_id=task_id,
            active_file=active_file,
            repo_root=None,
            assembled_prompt=assembled_prompt,
            tokenized_prompt=tokenized_prompt,
            symbol_context=symbol_ctx
        )

        # Get value and verify
        cached = ContextCache.get(task_id, active_file)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.assembled_prompt, assembled_prompt)
        self.assertEqual(cached.tokenized_prompt, tokenized_prompt)
        self.assertEqual(cached.symbol_context, symbol_ctx)

    def test_cache_hit_with_different_task_id(self):
        active_file = "app/main.py"
        symbol_ctx = ContextPackage(goal="optimize function", primary_symbol=None, previous_attempts=[])

        # Cache with task_id_1
        ContextCache.set(
            task_id="task-1",
            active_file=active_file,
            repo_root=None,
            assembled_prompt="prompt-1",
            tokenized_prompt=[1],
            symbol_context=symbol_ctx
        )

        # Try to retrieve with task_id_2 (should still match on active_file and files hash!)
        cached = ContextCache.get("task-2", active_file)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.symbol_context, symbol_ctx)

    @patch("context.context_builder.SessionLocal")
    @patch("context.goal_analyzer.GoalAnalyzer.analyze")
    def test_context_builder_cache_bypass(self, mock_analyze, mock_session_local):
        # Test that ContextBuilder returns the cached SymbolContext package without executing DB queries on cache hit
        task_id = "task-cache-bypass"
        active_file = "src/service.py"
        symbol_ctx = ContextPackage(goal="explain active file", primary_symbol=None, previous_attempts=[])

        # Preset the cache
        ContextCache.set(
            task_id=task_id,
            active_file=active_file,
            repo_root=None,
            assembled_prompt=None,
            tokenized_prompt=None,
            symbol_context=symbol_ctx
        )

        # Create state mock
        state = MagicMock()
        state.task_id = task_id
        state.runtime_context = MagicMock()
        state.runtime_context.active_file = active_file

        # Call ContextBuilder and verify it hits the cache
        builder = ContextBuilder(retrieval_pipeline=None, state_manager=None)
        
        # Build planning context (it shouldn't touch SessionLocal/database because of cache hit)
        result = builder.build_planning_context("explain active file", state=state)
        
        self.assertEqual(result, symbol_ctx)
        mock_session_local.assert_not_called()

if __name__ == "__main__":
    unittest.main()
