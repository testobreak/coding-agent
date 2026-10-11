# execution/inline_executor.py
from execution.inline_engine import InlineEngine

class InlineExecutor(InlineEngine):
    """
    Proposed design alias for InlineEngine.
    Retrieves active context, generates docstrings or small edits, and answers questions.
    """
    def run(self, query: str, context: dict = None, on_progress=None):
        return self.handle(query, context, on_progress=on_progress)
