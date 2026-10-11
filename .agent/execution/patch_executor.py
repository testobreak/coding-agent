# execution/patch_executor.py
from execution.patch_handler import PatchHandler

class PatchExecutor(PatchHandler):
    """
    Proposed design alias for PatchHandler.
    Resolves symbol, locates AST span, generates patches, and validates.
    """
    def run(self, query: str, context: dict = None, on_progress=None):
        return self.handle(query, context, on_progress=on_progress)
