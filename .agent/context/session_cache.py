# context/session_cache.py
#
# Session Context Cache for Cursor-like hot state preservation.
# Caches open tabs, diagnostics, cursor position, recent symbols, and the last context package.

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Tuple
from context.context_package import ContextPackage
from runtime.editor.models import Diagnostic

# Alias for compatibility with user expectations
ContextBundle = ContextPackage

@dataclass
class SessionContext:
    open_files: List[str] = field(default_factory=list)
    active_file: Optional[str] = None
    recent_symbols: List[str] = field(default_factory=list)
    last_context: Optional[ContextPackage] = None
    diagnostics: List[Diagnostic] = field(default_factory=list)
    cursor_positions: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    recent_edits: List[Any] = field(default_factory=list)
    task_id: Optional[str] = None

class SessionCache:
    _instances = {}

    @classmethod
    def get_session(cls, session_id: str = "default") -> SessionContext:
        if session_id not in cls._instances:
            cls._instances[session_id] = SessionContext()
        return cls._instances[session_id]

    @classmethod
    def clear(cls, session_id: str = "default"):
        if session_id in cls._instances:
            del cls._instances[session_id]
