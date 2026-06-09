# context/prompt_builder.py

from typing import Dict, Any, Union
import json
from context.prompt_context import PromptContext
from context.compression import ContextCompressor


class PromptBuilder:

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================

    def build_system_prompt(self) -> str:
        return """
You are an autonomous software engineering agent.

Your objectives:

- analyze repositories
- retrieve relevant code
- execute modifications safely
- validate architecture consistency
- repair failures autonomously
- avoid regressions
- minimize unnecessary edits

==================================================
EXECUTION RULES
==================================================

Always:

- prioritize active failures
- use retrieved code context
- preserve architecture
- prefer minimal diffs
- avoid speculative rewrites
- avoid duplicate modifications
- validate before major edits

==================================================
RETRIEVAL RULES
==================================================

Never modify code before:

1. retrieving related context
2. understanding dependencies
3. analyzing surrounding patterns

==================================================
FAILURE HANDLING
==================================================

If tests fail:

1. analyze root cause
2. identify minimal repair
3. avoid unrelated changes
4. preserve working behavior

==================================================
LOOP PREVENTION
==================================================

Avoid repeating:

- identical retrievals
- identical analyses
- repeated failed repairs

If stuck:
- replan
- change strategy
- narrow scope

==================================================
OUTPUT RULES
==================================================

Return structured reasoning.

Prefer:
- minimal actions
- html-style tags or structured commands
- architecture-safe execution
"""

    # =====================================================
    # SECTION BUILDERS
    # =====================================================

    def _format_section(self, title: str, content: str) -> str:
        return f"""==================================================
{title}
==================================================

{content}"""

    def build_task_section(self, ctx: PromptContext) -> str:
        return self._format_section("TASK", ctx.goal)

    def build_execution_context(self, ctx: PromptContext) -> str:
        content = f"""Status: {ctx.status or 'active'}
Current Step: {ctx.current_step or 'modify_file'}
Failed Steps count: {len(ctx.failed_steps or [])}
Test Failures count: {len(ctx.test_failures or [])}
Checkpoint Available: {'Yes' if ctx.current_plan else 'No'}"""
        return self._format_section("EXECUTION CONTEXT", content)

    def build_repository_context(self, ctx: PromptContext) -> str:
        file_paths = []
        symbols = []
        for chunk in (ctx.retrieved_chunks or []):
            file_path = chunk.get("file") or chunk.get("file_path") or ""
            symbol = chunk.get("symbol") or chunk.get("name") or ""
            if file_path and file_path not in file_paths:
                file_paths.append(file_path)
            if symbol and symbol not in symbols:
                symbols.append(symbol)

        files_str = "\n".join(f"- {path}" for path in file_paths[:10]) if file_paths else "No files targeted."
        symbols_str = "\n".join(f"- {symbol}" for symbol in symbols[:20]) if symbols else "No active symbols targeted."

        callers_list = []
        for c in (ctx.callers or []):
            if hasattr(c, "name"):
                callers_list.append(c.name)
            elif isinstance(c, dict):
                callers_list.append(c.get("name") or "")
        callers_str = "\n".join(f"- {name}" for name in callers_list if name) if callers_list else "No callers identified."

        callees_list = []
        for c in (ctx.callees or []):
            if hasattr(c, "name"):
                callees_list.append(c.name)
            elif isinstance(c, dict):
                callees_list.append(c.get("name") or "")
        callees_str = "\n".join(f"- {name}" for name in callees_list if name) if callees_list else "No callees identified."

        content = f"""FILES:
{files_str}

RELEVANT SYMBOLS:
{symbols_str}

CALLERS:
{callers_str}

CALLEES:
{callees_str}"""
        return self._format_section("REPOSITORY CONTEXT", content)

    def build_architecture_notes(self, ctx: PromptContext) -> str:
        notes = ctx.architecture_notes or []
        notes_str = "\n".join(f"- {note}" for note in notes) if notes else "No specific architectural constraints defined."
        return self._format_section("ARCHITECTURE NOTES", notes_str)

    def build_dependency_graph(self, ctx: PromptContext) -> str:
        symbols = []
        for chunk in (ctx.retrieved_chunks or []):
            symbol = chunk.get("symbol") or chunk.get("name") or ""
            if symbol and symbol not in symbols:
                symbols.append(symbol.split(".")[-1])

        if len(symbols) >= 2:
            graph_lines = []
            for i in range(min(len(symbols), 4)):
                indent = "  " * i
                arrow = " -> " if i > 0 else ""
                graph_lines.append(f"{indent}{arrow}{symbols[i]}")
            graph_str = "\n".join(graph_lines)
        else:
            graph_str = "No active dependency graph inferred from current context."

        return self._format_section("DEPENDENCY GRAPH", graph_str)

    def build_retrieved_code(self, ctx: PromptContext) -> str:
        """Build a section with retrieved code snippets.

        Uses ContextCompressor to truncate large files to a 1500 char limit
        and includes up to 10 snippets for richer context.
        """
        compressor = ContextCompressor(max_chunk_chars=1500)
        snippets = []
        for chunk in (ctx.retrieved_chunks or []):
            file_path = chunk.get("file") or chunk.get("file_path") or "unknown_file"
            content = chunk.get("content") or chunk.get("code") or ""
            if content:
                # Truncate safely using the compressor utility
                truncated = compressor.truncate(content, compressor.max_chunk_chars)
                snippets.append(f"File: {file_path}\nCode:\n{truncated}")
        code_str = "\n\n".join(snippets[:10]) if snippets else "No code snippets retrieved."
        return self._format_section("RETRIEVED CODE", code_str)

    def build_constraints(self, ctx: PromptContext) -> str:
        content = """- Do not introduce new external dependencies.
- Preserve existing transactional boundaries.
- Minimize editing footprint; prioritize active repair and verification."""
        return self._format_section("CONSTRAINTS", content)

    def build_output_contract(self, ctx: PromptContext) -> str:
        if ctx.current_step == "repair_file":
            format_str = "Return ONLY the unified diff of the repair patch."
        else:
            format_str = "1. Explanation of changes\n2. Modified files\n3. Unified diff\n4. Validation results"
        return self._format_section("OUTPUT CONTRACT", format_str)

    # =====================================================
    # EXECUTION PROMPT
    # =====================================================

    def build_execution_prompt(
        self,
        context: Union[PromptContext, Dict[str, Any]]
    ) -> str:
        """
        Enterprise-grade prompt compilation utilizing strongly-typed PromptContext.
        Enforces token-efficient constraints, precise edit targeting, and grounding.
        """
        if isinstance(context, dict):
            ctx = PromptContext.from_dict(context)
        else:
            ctx = context

        sections = [
            self.build_task_section(ctx),
            self.build_execution_context(ctx),
            self.build_repository_context(ctx),
            self.build_architecture_notes(ctx),
            self.build_dependency_graph(ctx),
            self.build_retrieved_code(ctx),
            self.build_constraints(ctx),
            self.build_output_contract(ctx)
        ]

        return "\n\n".join(sections)
