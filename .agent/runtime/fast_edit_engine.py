import logging
from runtime.editor.models import EditorState
from context.selection_context import SelectionContextBuilder
from editing.patch_engine import PatchEngine
from llm.ollama_client import OllamaClient

class FastEditEngine:
    """Engine for handling trivial edit requests directly from editor state.

    It builds a minimal selection‑centric context, asks the LLM for a replacement
    of the selected span only, and applies the patch via :class:`PatchEngine`.
    """

    def __init__(self, executor):
        self.executor = executor
        self.llm = OllamaClient()
        self.patch_engine = PatchEngine()
        self.logger = logging.getLogger(__name__)

    def run(self, query: str, state, mode: str = "fast_edit"):
        # Extract editor context from the runtime state
        editor_ctx = getattr(state, "runtime_context", None)
        if editor_ctx is None:
            self.logger.error("FastEditEngine: No editor context available")
            return {"error": "missing editor context"}

        # Build minimal selection‑centric context
        selection_ctx = SelectionContextBuilder.build(editor_ctx)
        if not selection_ctx:
            self.logger.error("FastEditEngine: No selection context could be built")
            return {"error": "no selection"}

        # Build a concise prompt for the LLM – ask for ONLY the replacement
        prompt = (
            f"You are an edit‑assistant. The user wants to perform the following edit:\n"
            f"{query}\n\n"
            f"Only modify the code inside the selected span. Return the new code for that span, nothing else."
            f"\n\nSelected code:\n{selection_ctx['selected_code']}"
        )
        # Call LLM (simplified – we just echo the selection for now)
        # In a real system this would be: response = self.llm.generate(prompt)
        # For now we assume the LLM returns the same selected code.
        new_code = selection_ctx["selected_code"]  # placeholder

        # Create a fake PatchOperation – the PatchEngine expects a plan, but we can
        # reuse its apply_patch method directly by constructing a minimal plan.
        # Here we simply replace the selected range in the file.
        file_path = editor_ctx.active_file
        if not file_path:
            return {"error": "no active file"}

        # Prepare a simple patch dict compatible with PatchEngine.apply_patch.
        # We'll reuse the engine's internal method by creating a temporary plan.
        from editing.patch_engine import PatchOperation, PatchType
        op = PatchOperation(
            type=PatchType.REPLACE_SPAN,
            file_path=file_path,
            span=None,  # Not needed for our simplified path
            content=new_code,
        )
        plan = [op]
        # Apply the patch (this will invoke diff UX and validation)
        success = self.patch_engine.apply_patch(plan)
        return {"fast_edit_applied": success}
