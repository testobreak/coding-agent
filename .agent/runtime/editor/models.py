# runtime/editor/models.py

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any

@dataclass
class Diagnostic:
    file: str
    line: int
    severity: str
    message: str
    source: str

@dataclass
class SymbolInfo:
    name: str
    symbol_type: str
    line_start: int
    line_end: int

@dataclass
class EditorContext:
    active_file: Optional[str] = None
    cursor_line: Optional[int] = None
    cursor_column: Optional[int] = None

    selected_text: Optional[str] = None
    selection_range: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None
    visible_range: Optional[Tuple[int, int]] = None

    open_tabs: List[str] = field(default_factory=list)

    diagnostics: List[Diagnostic] = field(default_factory=list)
    symbols: List[SymbolInfo] = field(default_factory=list)

    git_diff: Optional[str] = None
    unsaved_buffer: Optional[str] = None

@dataclass
class RuntimeContext:
    active_file: Optional[str] = None
    cursor_position: Optional[Tuple[int, int]] = None
    selection: Optional[str] = None
    selection_range: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None
    open_tabs: List[str] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)
    visible_range: Optional[Tuple[int, int]] = None
    unsaved_buffer: Optional[str] = None
    ide_context: Optional[Any] = None

@dataclass
class EditorState:
    active_file: Optional[str] = None
    cursor_line: Optional[int] = None
    cursor_column: Optional[int] = None
    selection_range: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None
    open_tabs: List[str] = field(default_factory=list)
    unsaved_buffer: Optional[str] = None
    diagnostics: List[Diagnostic] = field(default_factory=list)
