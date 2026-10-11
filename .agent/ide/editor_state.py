# ide/editor_state.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict

@dataclass
class Diagnostic:
    severity: str
    message: str
    line: int
    column: int
    source: str

@dataclass
class SelectionRange:
    start_line: int
    start_col: int
    end_line: int
    end_col: int

@dataclass
class EditorState:
    workspace_root: str
    active_file: str
    cursor_line: int
    cursor_column: int
    selection: Optional[SelectionRange] = None
    selected_text: Optional[str] = None
    open_tabs: List[str] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)
    unsaved_buffer: Optional[str] = None
    language: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
