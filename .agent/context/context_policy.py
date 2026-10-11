# context/context_policy.py
from typing import List
from core.execution_mode import TaskIntentMode as ExecutionMode
from context.context_mode import ContextMode

class ContextPolicy:
    include_local_symbol: bool = True
    include_repo_context: bool = True
    include_ui_context: bool = True
    include_memory: bool = True
    @staticmethod
    def choose(execution_mode: ExecutionMode, request: str = "", edit_span_confidence: float = 0.5) -> List[ContextMode]:
        """
        Determines the active context tiers based on the execution mode,
        the user request, and heuristics.
        """
        if execution_mode == ExecutionMode.INLINE:
            return [ContextMode.HOT]
            
        elif execution_mode == ExecutionMode.PATCH:
            # Under PATCH mode: always use HOT.
            # Add WARM only if edit span confidence is low.
            if edit_span_confidence < 0.85:
                return [ContextMode.HOT, ContextMode.WARM]
            else:
                return [ContextMode.HOT]
                
        else: # AGENT / ASSIST / ASSIST equivalent modes
            return [ContextMode.HOT, ContextMode.WARM, ContextMode.COLD]
