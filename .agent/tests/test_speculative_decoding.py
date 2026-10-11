# tests/test_speculative_decoding.py

import unittest
from unittest.mock import MagicMock, patch

from inference.speculative import SpeculativeDecoder
from llm.ollama_client import OllamaClient
from inference.router import TaskType

class TestSpeculativeDecoding(unittest.TestCase):

    def setUp(self):
        self.mock_target = MagicMock(spec=OllamaClient)
        self.mock_draft = MagicMock(spec=OllamaClient)
        self.decoder = SpeculativeDecoder(self.mock_target, self.mock_draft)

    def test_token_level_speculative_decoding_all_accepted(self):
        # Setup draft proposals
        # Step 1: Draft proposes "hello"
        # Step 2: Draft proposes "" (stop)
        self.mock_draft.chat.side_effect = ["h", "e", "l", "l", "o", ""]
        
        # Target validates all of them
        self.mock_target.chat.side_effect = ["h", "e", "l", "l", "o"]

        res = self.decoder.generate_speculative(prompt="greet", K=5)
        self.assertEqual(res, "hello")
        
        # Verify call counts:
        # Draft was called 6 times (5 chars + 1 empty stop)
        self.assertEqual(self.mock_draft.chat.call_count, 6)
        # Target was called 5 times to verify each token
        self.assertEqual(self.mock_target.chat.call_count, 5)

    def test_token_level_speculative_decoding_with_correction(self):
        # Draft proposes "world"
        self.mock_draft.chat.side_effect = ["w", "o", "r", "l", "d"]
        
        # Target validates "w", "o", but corrects "r" to "a", then loop terminates
        self.mock_target.chat.side_effect = ["w", "o", "a"]

        res = self.decoder.generate_speculative(prompt="earth", K=5)
        self.assertEqual(res, "woa")

    def test_line_level_speculative_editing_accept(self):
        # Draft proposes a full line of code
        self.mock_draft.chat.return_value = "def add(x, y): return x + y"
        
        # Target accepts the proposal
        self.mock_target.chat.return_value = "ACCEPT"

        on_progress = MagicMock()
        res = self.decoder.generate_speculative_line(
            prompt="write add function",
            context="math utilities",
            on_progress=on_progress
        )

        self.assertEqual(res, "def add(x, y): return x + y")
        on_progress.assert_any_call("status", "Drafting completion proposal using fast local model...")
        on_progress.assert_any_call("status", "Verifying speculative draft with target model...")
        on_progress.assert_any_call("status", "Speculative draft verified and accepted.")

    def test_line_level_speculative_editing_correction(self):
        # Draft proposes code with a typo/missing parameter
        self.mock_draft.chat.return_value = "def greet(): print('hello')"
        
        # Target corrects it to accept a name argument
        corrected_code = "def greet(name):\n    print(f'hello {name}')"
        self.mock_target.chat.return_value = corrected_code

        on_progress = MagicMock()
        res = self.decoder.generate_speculative_line(
            prompt="greet user function",
            context="user management",
            on_progress=on_progress
        )

        self.assertEqual(res, corrected_code)
        on_progress.assert_any_call("status", "Speculative draft corrected by target model.")
        on_progress.assert_any_call("token", f"\n[Correction]: {corrected_code}")

    @patch("llm.ollama_client.OllamaClient.chat")
    @patch("inference.router.ModelRouter.route")
    def test_ollama_client_speculative_chat_routing(self, mock_route, mock_chat):
        # Mock route mappings
        # target_model -> qwen2.5-coder:7b
        # draft_model -> qwen2.5-coder:1.5b
        mock_route.side_effect = ["qwen2.5-coder:7b", "qwen2.5-coder:1.5b"]

        client = OllamaClient(model="qwen2.5-coder:7b")
        
        # Mock the SpeculativeDecoder within speculative_chat call
        with patch("inference.speculative.SpeculativeDecoder.generate_speculative_line") as mock_spec_line:
            mock_spec_line.return_value = "speculative output"
            
            res = client.speculative_chat(
                messages=[{"role": "user", "content": "add function"}],
                task_type=TaskType.CHAT
            )
            
            self.assertEqual(res, "speculative output")
            mock_spec_line.assert_called_once()

if __name__ == "__main__":
    unittest.main()
