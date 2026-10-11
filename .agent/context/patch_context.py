# context/patch_context.py

import os
from dataclasses import dataclass, field
from typing import List, Tuple, Any, Optional

@dataclass
class PatchContext:
    instruction: str
    active_file: str
    cursor_span: Tuple[int, int]
    selected_code: str
    diagnostics: List[Any] = field(default_factory=list)
    relevant_symbols: List[Any] = field(default_factory=list)
    imports: List[Any] = field(default_factory=list)
    neighboring_code: str = ""


class PatchContextBuilder:
    """
    Stateless, Cursor-like Patch Context Builder.
    Builds minimal HOT / WARM context to maximize patch latency and precision.
    """
    def __init__(self, retrieval_pipeline=None):
        self.pipeline = retrieval_pipeline

    def build(self, editor_state: Any, instruction: str) -> PatchContext:
        active_file = getattr(editor_state, "active_file", "") or ""
        cursor_line = getattr(editor_state, "cursor_line", 1) or 1
        diagnostics = getattr(editor_state, "diagnostics", []) or []
        unsaved_buffer = getattr(editor_state, "unsaved_buffer", "") or ""

        # Determine selection range and cursor span
        selected_code = ""
        cursor_span = (1, 1)
        
        selection_range = getattr(editor_state, "selection_range", None)
        if selection_range:
            try:
                (start_line, _), (end_line, _) = selection_range
                cursor_span = (start_line, end_line)
            except Exception:
                pass

        # 1. HOT Context: Read active buffer + selection + surrounding lines
        neighboring_code = ""
        if active_file:
            repo_root = os.getcwd()
            if os.path.basename(repo_root) == ".agent":
                repo_root = os.path.dirname(repo_root)
            full_path = os.path.join(repo_root, active_file)
            
            content = unsaved_buffer
            if not content and os.path.exists(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception:
                    pass

            if content:
                lines = content.splitlines()
                if not selection_range:
                    # Default surrounding line budget of +-30 lines for HOT context
                    start_line = max(1, cursor_line - 30)
                    end_line = min(len(lines), cursor_line + 30)
                    cursor_span = (cursor_line, cursor_line)
                else:
                    start_line = max(1, cursor_span[0] - 30)
                    end_line = min(len(lines), cursor_span[1] + 30)
                
                selected_code = "\n".join(lines[cursor_span[0]-1:cursor_span[1]])
                neighboring_code = "\n".join(lines[start_line-1:end_line])

        # Stage 1: Return HOT only if prompt is simple and selection is present (high confidence)
        is_simple = any(kw in instruction.lower() for kw in ["add", "fix", "change", "check", "docstring", "comment", "logging"])
        if is_simple and selected_code:
            return PatchContext(
                instruction=instruction,
                active_file=active_file,
                cursor_span=cursor_span,
                selected_code=selected_code,
                diagnostics=diagnostics,
                relevant_symbols=[],
                imports=[],
                neighboring_code=neighboring_code
            )

        # Stage 2: Low-confidence / complex edit. Escalate and retrieve WARM context.
        relevant_symbols = []
        imports = []
        if self.pipeline and active_file:
            try:
                retrieved = self.pipeline.retrieve_relevant_chunks(
                    instruction, top_k=5, expand_context=False
                )
                for item in retrieved:
                    chunk = item.get("chunk", item)
                    relevant_symbols.append({
                        "name": chunk.get("symbol"),
                        "file": chunk.get("file"),
                        "start_line": chunk.get("start_line"),
                        "end_line": chunk.get("end_line"),
                        "code": chunk.get("code") or chunk.get("content")
                    })
                    if chunk.get("imports"):
                        imports.extend(chunk["imports"])
            except Exception as e:
                print(f"[PatchContextBuilder] Warm context retrieval warning: {e}")

        # Unique imports
        imports = list(set(imports))

        return PatchContext(
            instruction=instruction,
            active_file=active_file,
            cursor_span=cursor_span,
            selected_code=selected_code,
            diagnostics=diagnostics,
            relevant_symbols=relevant_symbols,
            imports=imports,
            neighboring_code=neighboring_code
        )


def patch_context_to_prompt_context(p_ctx: PatchContext) -> dict:
    """
    Translates PatchContext into a whitelisted, clean PromptContext dictionary structure.
    Strictly excludes failed_steps, reflections, tool outputs, execution logs, and runtime metrics.
    """
    retrieved_chunks = []
    
    # 1. Include neighboring code as the primary retrieved chunk
    if p_ctx.neighboring_code:
        retrieved_chunks.append({
            "file": p_ctx.active_file,
            "symbol": "active_file_focus",
            "start_line": p_ctx.cursor_span[0],
            "end_line": p_ctx.cursor_span[1],
            "content": p_ctx.neighboring_code
        })

    # 2. Append WARM retrieved relevant symbols
    for sym in p_ctx.relevant_symbols:
        retrieved_chunks.append({
            "file": sym["file"],
            "symbol": sym["name"],
            "start_line": sym["start_line"],
            "end_line": sym["end_line"],
            "content": sym["code"]
        })

    return {
        "goal": p_ctx.instruction,
        "status": "active",
        "current_step": "modify_file",
        "retrieved_chunks": retrieved_chunks,
        "test_failures": p_ctx.diagnostics,
        "active_symbols": [sym["name"] for sym in p_ctx.relevant_symbols if sym.get("name")],
        "pending_executions": [],
        "current_plan": [],
        "failed_steps": [],
        "repair_history": [],
        "reflections": [],
        "recent_tool_outputs": [],
        "execution_history": []
    }
