# tests/test_complexity_routing.py

import unittest
from unittest.mock import MagicMock, patch
import tempfile
import os

from runtime.runtime import Runtime
from routing.intent_router import RouteDecision, ExecutionMode, CostTier
from context.context_router import ContextBuilderEnum

class TestComplexityRouting(unittest.TestCase):

    def setUp(self):
        self.runtime = Runtime()
        self.runtime._services = MagicMock()
        
        # Setup basic state mocks
        self.mock_state = MagicMock()
        self.mock_state.runtime_context = None
        self.mock_state.status = "pending"
        self.mock_state.runtime_memory = MagicMock()
        self.mock_state.runtime_memory.total_iterations = 0
        self.runtime.state_manager.create_task.return_value = self.mock_state
        self.runtime.state_manager.task_id = None
        self.runtime.state_manager.state = None

        from editing.symbol_handle import SymbolHandle
        self.resolver_patcher = patch("editing.symbol_resolver.SymbolResolver.resolve")
        self.mock_resolve = self.resolver_patcher.start()
        self.mock_resolve.return_value = [
            SymbolHandle(
                symbol_id="sym_1",
                fqn="add",
                kind="function",
                file_path="math.py",
                start_line=1,
                end_line=2
            )
        ]
        self.addCleanup(self.resolver_patcher.stop)

    @patch("runtime.fast_path_router.FastPathRouter.route")
    def test_inline_list_files(self, mock_route):
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.INLINE,
            context_mode=ContextBuilderEnum.SELECTION,
            confidence=0.99,
            reason="Inline command",
            cost_tier=CostTier.CHEAP
        )
        
        # Mock file manager root
        self.runtime.file_manager.root = "/tmp"
        
        # Run list files
        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [("/tmp", [], ["main.py", "helper.py"])]
            self.runtime.run_goal("list files")
            
        # Verify that LLM was NOT called
        self.runtime.llm.chat.assert_not_called()

    @patch("runtime.fast_path_router.FastPathRouter.route")
    def test_inline_read_file(self, mock_route):
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.INLINE,
            context_mode=ContextBuilderEnum.SELECTION,
            confidence=0.99,
            reason="Inline command",
            cost_tier=CostTier.CHEAP
        )
        
        self.runtime.file_manager.read_file.return_value = "print('hello')"
        
        # Run read file
        self.runtime.run_goal("read file src/main.py")
        
        # Verify it read the file via FileManager
        self.runtime.file_manager.read_file.assert_called_with("src/main.py")
        self.runtime.llm.chat.assert_not_called()

    @patch("runtime.fast_path_router.FastPathRouter.route")
    @patch("engines.patch_engine._get_symbol_editor")
    def test_patch_execution_success(self, mock_get_editor, mock_route):
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.PATCH,
            context_mode=ContextBuilderEnum.SELECTION,
            confidence=0.95,
            reason="Single file edit",
            cost_tier=CostTier.MEDIUM
        )
        
        mock_editor = MagicMock()
        mock_editor.modify.return_value = {"success": True, "path": "math.py", "patch": "diff"}
        mock_get_editor.return_value = mock_editor
        
        # Run goal
        result = self.runtime.run_goal("add logging to def add in math.py")
        
        # Verify result and call
        self.assertEqual(result, "SUCCESS")
        mock_editor.modify.assert_called_once()

    @patch("runtime.fast_path_router.FastPathRouter.route")
    @patch("engines.patch_engine._get_symbol_editor")
    def test_patch_execution_one_shot_repair(self, mock_get_editor, mock_route):
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.PATCH,
            context_mode=ContextBuilderEnum.SELECTION,
            confidence=0.95,
            reason="Single file edit",
            cost_tier=CostTier.MEDIUM
        )
        
        mock_editor = MagicMock()
        mock_editor.modify.side_effect = [
            {"success": False, "error": "SyntaxError"},
            {"success": True, "path": "math.py", "patch": "diff"}
        ]
        mock_get_editor.return_value = mock_editor
        
        # Run goal
        result = self.runtime.run_goal("add logging to math.py")
        
        # Verify it attempted repair
        self.assertEqual(result, "SUCCESS")
        self.assertEqual(mock_editor.modify.call_count, 2)

    @patch("runtime.fast_path_router.FastPathRouter.route")
    @patch("engines.patch_engine._get_symbol_editor")
    def test_patch_execution_failed_rollback(self, mock_get_editor, mock_route):
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.PATCH,
            context_mode=ContextBuilderEnum.SELECTION,
            confidence=0.95,
            reason="Single file edit",
            cost_tier=CostTier.MEDIUM
        )
        
        mock_editor = MagicMock()
        mock_editor.modify.side_effect = [
            {"success": False, "error": "SyntaxError1"},
            {"success": False, "error": "SyntaxError2"}
        ]
        mock_get_editor.return_value = mock_editor
        
        # Run goal
        result = self.runtime.run_goal("add logging to math.py")
        
        # Verify double failure
        self.assertEqual(result, "FAILED: SyntaxError2")
        self.assertEqual(mock_editor.modify.call_count, 2)

if __name__ == "__main__":
    unittest.main()
