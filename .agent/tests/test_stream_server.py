# tests/test_stream_server.py

import unittest
import json
import threading
import time
import requests
from unittest.mock import patch, MagicMock
from http.server import HTTPServer

from runtime.server import AgentHTTPHandler
from runtime.runtime import Runtime
from routing.intent_router import RouteDecision, ExecutionMode, CostTier
from context.context_router import ContextBuilderEnum

class TestStreamServer(unittest.TestCase):
    server = None
    server_thread = None
    PORT = 8087

    @classmethod
    def setUpClass(cls):
        # Clear mock cache
        from inference.router import ModelRouter
        ModelRouter._cached_models = None
        ModelRouter._last_fetch_time = 0.0

        # Start the server in a background thread
        cls.server = HTTPServer(('localhost', cls.PORT), AgentHTTPHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        print(f"[TestServer] Started on port {cls.PORT}")

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            cls.server_thread.join()
            print("[TestServer] Stopped")

    @patch("runtime.fast_path_router.FastPathRouter.route")
    @patch("context.context_builder.ContextBuilder.build_planning_context")
    @patch("llm.ollama_client.OllamaClient.chat")
    def test_modify_sse_streaming(self, mock_chat, mock_build, mock_route):
        # Mock route to PATCH_EDIT
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.PATCH_EDIT,
            context_mode=ContextBuilderEnum.SELECTION,
            confidence=0.9,
            reason="Heuristic edit",
            cost_tier=CostTier.CHEAP
        )

        # Mock context package
        mock_context = MagicMock()
        mock_context.goal = "add log"
        mock_context.primary_symbol = None
        mock_context.related_files = ["src/test.py"]
        mock_context.retrieved_chunks = []
        mock_build.return_value = mock_context

        # Mock LLM chat return generator or response
        mock_chat.return_value = "<<<<<<< SEARCH\noriginal\n=======\nmodified\n>>>>>>> REPLACE"

        payload = {
            "query": "add logging to test.py",
            "editor_context": {
                "active_file": "src/test.py",
                "open_tabs": ["src/test.py"]
            }
        }

        # Mock self.engine.run inside Runtime so it doesn't fail
        runtime = AgentHTTPHandler.get_runtime()
        with patch.object(runtime.engine, "run") as mock_engine_run:
            response = requests.post(f"http://localhost:{self.PORT}/modify", json=payload, stream=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "text/event-stream")

        events = []
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith("data:"):
                    event_data = json.loads(line_str.replace("data:", "").strip())
                    events.append(event_data)

        self.assertTrue(len(events) >= 2)
        # Verify we got status events
        status_events = [e for e in events if e["type"] == "status"]
        self.assertTrue(len(status_events) > 0)
        self.assertEqual(status_events[0]["content"], "Thinking...")

        # Verify we got the final done event with patch payload
        done_events = [e for e in events if e["type"] == "done"]
        self.assertEqual(len(done_events), 1)
        self.assertEqual(done_events[0]["content"]["status"], "success")

    @patch("runtime.fast_path_router.FastPathRouter.route")
    @patch("context.context_builder.ContextBuilder.build_planning_context")
    @patch("llm.ollama_client.OllamaClient.chat")
    def test_chat_sse_streaming_assist(self, mock_chat, mock_build, mock_route):
        # Mock route to ASSIST
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.ASSIST,
            context_mode=ContextBuilderEnum.REPOSITORY,
            confidence=0.9,
            reason="Heuristic assist",
            cost_tier=CostTier.CHEAP
        )

        mock_context = MagicMock()
        mock_context.goal = "explain service"
        mock_context.primary_symbol = None
        mock_context.related_files = []
        mock_context.retrieved_chunks = []
        mock_build.return_value = mock_context

        # Mock streaming tokens generator from Ollama
        def token_stream():
            yield "Hello"
            yield " "
            yield "World"
        mock_chat.return_value = token_stream()

        payload = {
            "query": "explain this code",
            "editor_context": {
                "active_file": "src/test.py",
                "open_tabs": ["src/test.py"]
            }
        }

        response = requests.post(f"http://localhost:{self.PORT}/chat", json=payload, stream=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Type"), "text/event-stream")

        events = []
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith("data:"):
                    event_data = json.loads(line_str.replace("data:", "").strip())
                    events.append(event_data)

        # Verify token events
        token_events = [e for e in events if e["type"] == "token"]
        tokens = [e["content"] for e in token_events]
        self.assertEqual(tokens, ["Hello", " ", "World"])

        # Verify done event
        done_events = [e for e in events if e["type"] == "done"]
        self.assertEqual(len(done_events), 1)


if __name__ == "__main__":
    unittest.main()
