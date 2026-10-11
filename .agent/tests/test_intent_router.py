# tests/test_intent_router.py

import unittest
from unittest.mock import patch, MagicMock

from routing.intent_router import IntentRouter, ExecutionMode, CostTier
from context.context_router import ContextBuilderEnum

class TestIntentRouter(unittest.TestCase):

    @patch("llm.ollama_client.OllamaClient.chat")
    def test_llm_routing_success(self, mock_chat):
        # Mock successful LLM classification
        mock_chat.return_value = """{
            "execution_mode": "inline_edit",
            "context_mode": "selection",
            "confidence": 0.95,
            "reason": "Test variable renaming",
            "cost_tier": "cheap"
        }"""

        decision = IntentRouter.route("rename x to y")

        # Verify that it matched the LLM classification
        self.assertIsNotNone(decision)
        self.assertEqual(decision.execution_mode, ExecutionMode.INLINE_EDIT)
        self.assertEqual(decision.context_mode, ContextBuilderEnum.SELECTION)
        self.assertEqual(decision.cost_tier, CostTier.CHEAP)
        self.assertEqual(decision.reason, "Test variable renaming")
        self.assertEqual(decision.confidence, 0.95)

        # Verify task_type passed to chat call
        from inference.router import TaskType
        mock_chat.assert_called_once()
        self.assertEqual(mock_chat.call_args[1].get("task_type"), TaskType.RETRIEVAL)

    @patch("llm.ollama_client.OllamaClient.chat")
    def test_llm_routing_invalid_json_fallback(self, mock_chat):
        # Return invalid JSON
        mock_chat.return_value = "invalid json response"

        # The query "explain this" would heuristic-route to ASSIST and REPOSITORY context
        decision = IntentRouter.route("explain this")

        self.assertIsNotNone(decision)
        self.assertEqual(decision.execution_mode, ExecutionMode.ASSIST)
        self.assertEqual(decision.context_mode, ContextBuilderEnum.REPOSITORY)
        self.assertTrue("explain" in decision.reason.lower() or "assist" in decision.reason.lower())

    @patch("llm.ollama_client.OllamaClient.chat")
    def test_llm_routing_exception_fallback(self, mock_chat):
        # Simulate connection error/exception
        mock_chat.side_effect = Exception("Ollama disconnected")

        # The query "rename variable x to leave_days" heuristic-routes to PATCH_EDIT (or inline depending on heuristics)
        # In IntentRouter heuristics, "rename method" or modify keywords route to PATCH_EDIT or inline_edit
        decision = IntentRouter.route("rename variable x to leave_days")

        self.assertIsNotNone(decision)
        # Should fallback gracefully without throwing exception
        self.assertIn(decision.execution_mode, [ExecutionMode.PATCH_EDIT, ExecutionMode.INLINE_EDIT, ExecutionMode.AGENT])


if __name__ == "__main__":
    unittest.main()
