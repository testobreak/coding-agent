# ide/bridge.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Any, Dict
import difflib
from ide.editor_state import EditorState, SelectionRange, Diagnostic

@dataclass
class IDEContext:
    active_file: str
    cursor_line: int
    selection_start: Optional[int]
    selection_end: Optional[int]
    selected_text: Optional[str]
    diagnostics: List[Any]
    open_tabs: List[str]

    @classmethod
    def from_dict(cls, data: dict) -> "IDEContext":
        """
        Robustly parses a raw JSON payload from the IDE extension into a strongly-typed IDEContext.
        """
        active_file = data.get("active_file") or ""
        
        # Parse cursor position
        cursor_pos = data.get("cursor_position")
        cursor_line = 1
        if isinstance(cursor_pos, (list, tuple)):
            cursor_line = cursor_pos[0]
        elif isinstance(cursor_pos, int):
            cursor_line = cursor_pos
            
        # Parse selection ranges
        sel_range = data.get("selection_range")
        sel_start = None
        sel_end = None
        if sel_range and isinstance(sel_range, (list, tuple)) and len(sel_range) == 2:
            if isinstance(sel_range[0], (list, tuple)):
                sel_start = sel_range[0][0]
            elif isinstance(sel_range[0], int):
                sel_start = sel_range[0]
                
            if isinstance(sel_range[1], (list, tuple)):
                sel_end = sel_range[1][0]
            elif isinstance(sel_range[1], int):
                sel_end = sel_range[1]

        selected_text = data.get("selected_text") or data.get("selection")
        diagnostics = data.get("diagnostics") or []
        open_tabs = data.get("open_tabs") or []

        return cls(
            active_file=active_file,
            cursor_line=cursor_line,
            selection_start=sel_start,
            selection_end=sel_end,
            selected_text=selected_text,
            diagnostics=diagnostics,
            open_tabs=open_tabs
        )


class IDEAdapter(ABC):
    @abstractmethod
    def parse_payload(self, raw_data: dict) -> IDEContext:
        pass

    @abstractmethod
    def parse_editor_state(self, raw_data: dict) -> EditorState:
        pass

    @abstractmethod
    def format_proposal(self, file_path: str, original_content: str, patched_content: str) -> dict:
        pass


class VSCodeAdapter(IDEAdapter):
    def parse_payload(self, raw_data: dict) -> IDEContext:
        return IDEContext.from_dict(raw_data)

    def parse_editor_state(self, raw_data: dict) -> EditorState:
        workspace_root = raw_data.get("workspace_root") or ""
        active_file = raw_data.get("active_file") or ""
        
        cursor_line = 1
        cursor_column = 0
        cursor_pos = raw_data.get("cursor_position")
        if isinstance(cursor_pos, (list, tuple)):
            cursor_line = cursor_pos[0]
            if len(cursor_pos) > 1:
                cursor_column = cursor_pos[1]
        elif isinstance(cursor_pos, int):
            cursor_line = cursor_pos

        sel = None
        sel_range = raw_data.get("selection_range")
        if sel_range and isinstance(sel_range, dict):
            sel = SelectionRange(
                start_line=sel_range.get("start_line", 1),
                start_col=sel_range.get("start_col", 0),
                end_line=sel_range.get("end_line", 1),
                end_col=sel_range.get("end_col", 0)
            )
        elif sel_range and isinstance(sel_range, (list, tuple)) and len(sel_range) == 2:
            try:
                sel = SelectionRange(
                    start_line=sel_range[0][0] if isinstance(sel_range[0], (list, tuple)) else sel_range[0],
                    start_col=sel_range[0][1] if isinstance(sel_range[0], (list, tuple)) else 0,
                    end_line=sel_range[1][0] if isinstance(sel_range[1], (list, tuple)) else sel_range[1],
                    end_col=sel_range[1][1] if isinstance(sel_range[1], (list, tuple)) else 0
                )
            except Exception:
                pass

        selected_text = raw_data.get("selected_text") or raw_data.get("selection")
        if isinstance(selected_text, dict):
            selected_text = None

        open_tabs = raw_data.get("open_tabs") or []
        diagnostics = []
        raw_diags = raw_data.get("diagnostics") or []
        for d in raw_diags:
            if isinstance(d, dict):
                diagnostics.append(Diagnostic(
                    severity=d.get("severity") or "error",
                    message=d.get("message") or d.get("text") or "",
                    line=d.get("line") or d.get("lnum", 1),
                    column=d.get("column") or d.get("col", 0),
                    source=d.get("source") or "vscode"
                ))

        return EditorState(
            workspace_root=workspace_root,
            active_file=active_file,
            cursor_line=cursor_line,
            cursor_column=cursor_column,
            selection=sel,
            selected_text=selected_text,
            open_tabs=open_tabs,
            diagnostics=diagnostics,
            unsaved_buffer=raw_data.get("unsaved_buffer"),
            language=raw_data.get("language"),
            metadata=raw_data.get("metadata") or {}
        )

    def format_proposal(self, file_path: str, original_content: str, patched_content: str) -> dict:
        return {
            "client": "vscode",
            "file_path": file_path,
            "action": "diff_preview",
            "original": original_content,
            "patched": patched_content
        }


class JetBrainsAdapter(IDEAdapter):
    def parse_payload(self, raw_data: dict) -> IDEContext:
        context = IDEContext.from_dict(raw_data)
        if "jetbrains" in raw_data.get("client", "").lower():
            context.cursor_line = max(1, context.cursor_line)
        return context

    def parse_editor_state(self, raw_data: dict) -> EditorState:
        # JetBrains is 0-indexed in SDK, we align to 1-indexed
        workspace_root = raw_data.get("workspace_root") or ""
        active_file = raw_data.get("active_file") or ""
        
        cursor_line = 1
        cursor_column = 0
        cursor_pos = raw_data.get("cursor_position")
        if isinstance(cursor_pos, (list, tuple)):
            cursor_line = max(1, cursor_pos[0])
            if len(cursor_pos) > 1:
                cursor_column = cursor_pos[1]
        elif isinstance(cursor_pos, int):
            cursor_line = max(1, cursor_pos)

        sel = None
        sel_range = raw_data.get("selection_range")
        if sel_range and isinstance(sel_range, dict):
            sel = SelectionRange(
                start_line=max(1, sel_range.get("start_line", 1)),
                start_col=sel_range.get("start_col", 0),
                end_line=max(1, sel_range.get("end_line", 1)),
                end_col=sel_range.get("end_col", 0)
            )

        selected_text = raw_data.get("selected_text") or raw_data.get("selection")
        if isinstance(selected_text, dict):
            selected_text = None

        open_tabs = raw_data.get("open_tabs") or []
        diagnostics = []
        raw_diags = raw_data.get("diagnostics") or []
        for d in raw_diags:
            if isinstance(d, dict):
                diagnostics.append(Diagnostic(
                    severity=d.get("severity") or "error",
                    message=d.get("message") or d.get("text") or "",
                    line=max(1, d.get("line") or d.get("lnum", 1)),
                    column=d.get("column") or d.get("col", 0),
                    source=d.get("source") or "jetbrains"
                ))

        return EditorState(
            workspace_root=workspace_root,
            active_file=active_file,
            cursor_line=cursor_line,
            cursor_column=cursor_column,
            selection=sel,
            selected_text=selected_text,
            open_tabs=open_tabs,
            diagnostics=diagnostics,
            unsaved_buffer=raw_data.get("unsaved_buffer"),
            language=raw_data.get("language"),
            metadata=raw_data.get("metadata") or {}
        )

    def format_proposal(self, file_path: str, original_content: str, patched_content: str) -> dict:
        return {
            "client": "jetbrains",
            "file_path": file_path,
            "action": "show_side_by_side",
            "original": original_content,
            "patched": patched_content
        }


class NeovimAdapter(IDEAdapter):
    def parse_payload(self, raw_data: dict) -> IDEContext:
        context = IDEContext.from_dict(raw_data)
        raw_diags = raw_data.get("diagnostics", [])
        formatted_diags = []
        for d in raw_diags:
            if isinstance(d, dict):
                formatted_diags.append({
                    "file": d.get("filename") or d.get("bufname") or context.active_file,
                    "line": d.get("lnum", 1),
                    "message": d.get("text") or d.get("message", "")
                })
            else:
                formatted_diags.append(d)
        context.diagnostics = formatted_diags
        return context

    def parse_editor_state(self, raw_data: dict) -> EditorState:
        workspace_root = raw_data.get("workspace_root") or ""
        active_file = raw_data.get("active_file") or ""
        
        cursor_line = 1
        cursor_column = 0
        cursor_pos = raw_data.get("cursor_position")
        if isinstance(cursor_pos, (list, tuple)):
            cursor_line = cursor_pos[0]
            if len(cursor_pos) > 1:
                cursor_column = cursor_pos[1]
        elif isinstance(cursor_pos, int):
            cursor_line = cursor_pos

        sel = None
        sel_range = raw_data.get("selection_range")
        if sel_range and isinstance(sel_range, dict):
            sel = SelectionRange(
                start_line=sel_range.get("start_line", 1),
                start_col=sel_range.get("start_col", 0),
                end_line=sel_range.get("end_line", 1),
                end_col=sel_range.get("end_col", 0)
            )

        selected_text = raw_data.get("selected_text") or raw_data.get("selection")
        if isinstance(selected_text, dict):
            selected_text = None

        open_tabs = raw_data.get("open_tabs") or []
        
        # Parse Neovim Quickfix format into Diagnostic
        diagnostics = []
        raw_diags = raw_data.get("diagnostics") or []
        for d in raw_diags:
            if isinstance(d, dict):
                diagnostics.append(Diagnostic(
                    severity=d.get("type") or "error",
                    message=d.get("text") or d.get("message") or "",
                    line=d.get("lnum") or d.get("line", 1),
                    column=d.get("col") or d.get("column", 0),
                    source=d.get("source") or "neovim"
                ))

        return EditorState(
            workspace_root=workspace_root,
            active_file=active_file,
            cursor_line=cursor_line,
            cursor_column=cursor_column,
            selection=sel,
            selected_text=selected_text,
            open_tabs=open_tabs,
            diagnostics=diagnostics,
            unsaved_buffer=raw_data.get("unsaved_buffer"),
            language=raw_data.get("language"),
            metadata=raw_data.get("metadata") or {}
        )

    def format_proposal(self, file_path: str, original_content: str, patched_content: str) -> dict:
        diff_lines = difflib.unified_diff(
            original_content.splitlines(),
            patched_content.splitlines(),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=""
        )
        return {
            "client": "neovim",
            "file_path": file_path,
            "action": "unified_diff",
            "diff": "\n".join(diff_lines)
        }


class IDEBridge:
    @staticmethod
    def get_adapter(client_name: str) -> IDEAdapter:
        name = (client_name or "").lower()
        if "jetbrains" in name or "idea" in name:
            return JetBrainsAdapter()
        elif "neovim" in name or "nvim" in name or "vim" in name:
            return NeovimAdapter()
        return VSCodeAdapter()
