# execution/assist_executor.py
from execution.assist_engine import AssistEngine

class AssistExecutor(AssistEngine):
    """
    Proposed design alias for AssistEngine.
    Explains methods, unit tests, and conducts semantic queries.
    """
    def run(self, query: str, context: dict = None, on_progress=None):
        return self.handle(query, context, on_progress=on_progress)
