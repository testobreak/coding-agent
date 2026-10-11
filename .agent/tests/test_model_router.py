# tests/test_model_router.py

import unittest
from unittest.mock import patch, MagicMock
import time

from inference.router import TaskType, ModelRouter

class TestModelRouter(unittest.TestCase):

    def test_parse_size_details(self):
        router = ModelRouter()
        
        # Test parsing from details.parameter_size
        self.assertEqual(router._parse_size({"details": {"parameter_size": "1.5B"}}), 1.5)
        self.assertEqual(router._parse_size({"details": {"parameter_size": "7.6B"}}), 7.6)
        self.assertEqual(router._parse_size({"details": {"parameter_size": "32b"}}), 32.0)
        self.assertEqual(router._parse_size({"details": {"parameter_size": "70B"}}), 70.0)

    def test_parse_size_fallback_name(self):
        router = ModelRouter()
        
        # Test parsing fallback from name when details is missing
        self.assertEqual(router._parse_size({"name": "qwen2.5-coder:1.5b-base"}), 1.5)
        self.assertEqual(router._parse_size({"name": "llama3.1:8b"}), 8.0)
        self.assertEqual(router._parse_size({"name": "phi3:3.8b"}), 3.8)
        self.assertEqual(router._parse_size({"name": "codellama:34b"}), 34.0)
        self.assertEqual(router._parse_size({"name": "gemma2:2b"}), 2.0)
        # Test fallback with no parseable size
        self.assertIsNone(router._parse_size({"name": "qwen2.5-coder:latest"}))

    @patch("requests.get")
    def test_routing_with_pulled_models(self, mock_get):
        # Setup mock pulled models
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {
                    "name": "qwen2.5-coder:1.5b-base",
                    "details": {"parameter_size": "1.5B"}
                },
                {
                    "name": "llama3.1:8b",
                    "details": {"parameter_size": "8.0B"}
                },
                {
                    "name": "qwen2.5-coder:7b",
                    "details": {"parameter_size": "7.6B"}
                },
                {
                    "name": "nomic-embed-text:latest",
                    "details": {"parameter_size": "137M"}
                }
            ]
        }
        mock_get.return_value = mock_response

        # Clear cache for the test
        ModelRouter._cached_models = None
        ModelRouter._last_fetch_time = 0.0

        router = ModelRouter(default_model="default-qwen:7b")

        # 1. RETRIEVAL should route to the 1.5B model
        self.assertEqual(router.route(TaskType.RETRIEVAL), "qwen2.5-coder:1.5b-base")

        # 2. PLAN should route to qwen2.5-coder:7b (preferring coder over llama3.1:8b)
        self.assertEqual(router.route(TaskType.PLAN), "qwen2.5-coder:7b")

        # 3. EDIT_COMPLEX (32B+) should fallback to default since no 32B model is pulled
        self.assertEqual(router.route(TaskType.EDIT_COMPLEX), "default-qwen:7b")

        # Verify embed model was filtered out and not matched for retrieval
        models = router.get_available_models()
        self.assertFalse(any(m["name"] == "nomic-embed-text:latest" for m in models))

    @patch("requests.get")
    def test_routing_with_32b_model(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {
                    "name": "qwen2.5-coder:7b",
                    "details": {"parameter_size": "7.6B"}
                },
                {
                    "name": "qwen2.5-coder:32b",
                    "details": {"parameter_size": "32B"}
                }
            ]
        }
        mock_get.return_value = mock_response

        ModelRouter._cached_models = None
        ModelRouter._last_fetch_time = 0.0

        router = ModelRouter(default_model="default-qwen:7b")

        # EDIT_COMPLEX (32B+) should match the 32B model
        self.assertEqual(router.route(TaskType.EDIT_COMPLEX), "qwen2.5-coder:32b")

    @patch("requests.get")
    def test_fallback_on_unreachable_server(self, mock_get):
        # Simulate connection error
        mock_get.side_effect = Exception("Ollama server down")

        ModelRouter._cached_models = None
        ModelRouter._last_fetch_time = 0.0

        router = ModelRouter(default_model="fallback-model:7b")
        
        # All tasks should gracefully fallback to default model
        self.assertEqual(router.route(TaskType.RETRIEVAL), "fallback-model:7b")
        self.assertEqual(router.route(TaskType.EDIT_COMPLEX), "fallback-model:7b")

    @patch("requests.get")
    def test_caching_behavior(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}
        mock_get.return_value = mock_response

        ModelRouter._cached_models = None
        ModelRouter._last_fetch_time = 0.0

        router = ModelRouter()
        
        # Trigger route multiple times
        router.route(TaskType.PLAN)
        router.route(TaskType.RETRIEVAL)
        router.route(TaskType.EDIT_COMPLEX)

        # requests.get should have been called exactly once because of cache TTL
        mock_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
