# context/working_set.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class WorkingSet:
    """
    Compact canonical context object keeping hot RAM allocations <200MB.
    Only holds active editor indicators in hot memory; large logs and histories
    remain cold on disk.
    """
    active_file: Optional[str] = None
    active_symbol: Optional[str] = None
    retrieved_candidates: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_editor_state(cls, editor_state: Any, candidates: List[Dict[str, Any]] = None) -> "WorkingSet":
        active_file = getattr(editor_state, "active_file", None)
        active_symbol = getattr(editor_state, "active_symbol", None)
        
        diagnostics = []
        raw_diags = getattr(editor_state, "diagnostics", []) or []
        for d in raw_diags:
            if isinstance(d, dict):
                diagnostics.append(d)
            elif hasattr(d, "message"):
                diagnostics.append({
                    "file": getattr(d, "file", active_file),
                    "line": getattr(d, "line", 1),
                    "severity": getattr(d, "severity", "error"),
                    "message": getattr(d, "message", "")
                })

        return cls(
            active_file=active_file,
            active_symbol=active_symbol,
            retrieved_candidates=candidates or [],
            diagnostics=diagnostics
        )
