# context/providers/hot_provider.py
import os
from dataclasses import dataclass
from typing import List, Tuple, Any

@dataclass
class HotContext:
    active_file: str
    cursor_span: Tuple[int, int]
    selection: str
    diagnostics: List[Any]
    user_request: str

class HotProvider:
    def __init__(self, state: Any):
        self.state = state

    def resolve(self) -> dict:
        editor_state = getattr(self.state.runtime_memory, "editor_state", None) if getattr(self.state, "runtime_memory", None) else None
        active_file = getattr(editor_state, "active_file", "") if editor_state else ""
        
        diagnostics = getattr(self.state.runtime_memory, "diagnostics", []) if getattr(self.state, "runtime_memory", None) else []
        user_request = getattr(self.state, "goal", "")
        
        cursor_line = getattr(editor_state, "cursor_line", 1) if editor_state else 1
        selection = getattr(editor_state, "selection_range", "") or getattr(editor_state, "unsaved_buffer", "") if editor_state else ""
        
        # Keep ±30 lines around cursor line if active_file exists
        cursor_span = (1, 1)
        if active_file and os.path.exists(active_file) and not selection:
            try:
                with open(active_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                start = max(0, cursor_line - 30)
                end = min(len(lines), cursor_line + 30)
                selection = "".join(lines[start:end])
                cursor_span = (start + 1, end)
            except Exception:
                pass
                
        return {
            "active_file": active_file,
            "cursor_span": cursor_span,
            "selection": selection,
            "diagnostics": diagnostics,
            "user_request": user_request
        }
