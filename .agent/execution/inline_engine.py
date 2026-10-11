# execution/inline_engine.py
import os
from inference.router import TaskType

class InlineEngine:
    """Lightweight, stateless inline completion and edit engine."""
    
    def __init__(self, runtime):
        self.runtime = runtime

    def handle(self, prompt: str, editor_state, on_progress=None) -> str:
        if on_progress:
            on_progress("status", "Executing inline suggestion...")

        # Extract code selection or active buffer context
        code = getattr(editor_state, "selection", None) or ""
        if not code and getattr(editor_state, "active_file", None):
            try:
                repo_root = os.getcwd()
                if os.path.basename(repo_root) == ".agent":
                    repo_root = os.path.dirname(repo_root)
                full_path = os.path.join(repo_root, editor_state.active_file)
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        code = f.read()
            except Exception:
                pass

        # Build clean, direct prompt for the LLM
        quick_prompt = f"""You are a precise, fast developer assistant.
CONTEXT CODE:
{code}

USER REQUEST:
{prompt}

Respond directly and concisely. Return only the direct answer or the requested code suggestion.
"""
        if on_progress:
            token_stream = self.runtime.llm.chat([
                {"role": "user", "content": quick_prompt}
            ], task_type=TaskType.CHAT, stream=True)
            full_response = []
            for token in token_stream:
                full_response.append(token)
                on_progress("token", token)
            return "".join(full_response)
        else:
            return self.runtime.llm.chat([
                {"role": "user", "content": quick_prompt}
            ], task_type=TaskType.CHAT)
