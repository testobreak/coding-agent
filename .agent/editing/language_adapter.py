# editing/language_adapter.py
#
# Language Adapter Layer — sits between EditExecutor and the concrete
# patch generation + application engines.
#
# Architecture:
#   EditExecutor
#       │
#       ▼
#   LanguageAdapter  (base class — language-agnostic contract)
#       │
#       ├── JavaAdapter      → uses tree-sitter / regex for Java AST
#       ├── PythonAdapter    → uses Python ast / tree-sitter
#       └── TypeScriptAdapter → uses ts-morph compatible layer
#
# Each adapter maps an EditPlan to a concrete Patch without the planner or
# executor needing to know anything about the target language.

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional

from editing.models.edit_plan import EditPlan
from editing.models.edit_operation import EditOperation
from editing.patch import Patch
from editing.symbol_handle import SymbolHandle

logger = logging.getLogger(__name__)

# File extension → language
_EXT_MAP = {
    ".java": "java",
    ".kt": "kotlin",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
}


def detect_language(file_path: Optional[str]) -> str:
    """Detect language from file extension. Returns ``"unknown"`` if unrecognised."""
    if not file_path:
        return "unknown"
    _, ext = os.path.splitext(file_path)
    return _EXT_MAP.get(ext.lower(), "unknown")


class LanguageAdapter(ABC):
    """Abstract base for language-specific edit adapters.

    Implementors receive a resolved :class:`SymbolHandle` and an
    :class:`EditPlan` and must return a :class:`Patch` without writing
    anything to disk.
    """

    @property
    @abstractmethod
    def supported_languages(self) -> list[str]:
        """Return the language identifiers this adapter supports."""

    @abstractmethod
    def build_patch(
        self,
        plan: EditPlan,
        symbol: SymbolHandle,
        original_content: str,
    ) -> Patch:
        """Translate an EditPlan into a Patch.

        Parameters
        ----------
        plan : EditPlan
            The high-level edit intent.
        symbol : SymbolHandle
            Resolved symbol metadata (AST boundaries, qualified name, etc.).
        original_content : str
            Current full text of the file being modified.

        Returns
        -------
        Patch
            A Patch object ready to be applied and validated.
            Must NOT write to disk — that is EditExecutor's responsibility.
        """


# ─────────────────────────────────────────────────────────────────────────────
# Concrete adapters
# ─────────────────────────────────────────────────────────────────────────────

class GenericAdapter(LanguageAdapter):
    """Generic adapter that delegates to the existing SymbolEditor pipeline.

    This keeps backward-compatibility during the migration phase while all
    languages share the same tree-sitter + PatchGenerator + PatchApplier flow
    that already exists in SymbolEditor.edit().

    Language-specific adapters (JavaAdapter, PythonAdapter, …) can be added
    later to optimise for each language's AST library without breaking the
    contract.
    """

    @property
    def supported_languages(self) -> list[str]:
        # Handles everything — a more specific adapter takes priority if registered
        return ["*"]

    def build_patch(
        self,
        plan: EditPlan,
        symbol: SymbolHandle,
        original_content: str,
        *,
        # Extra injected collaborators (set by EditExecutor)
        ast_locator=None,
        patch_generator=None,
        patch_applier=None,
        execution_context: str = "",
        symbol_info=None,
    ) -> Patch:
        from editing.ast_locator import ASTNodeInfo

        resolved_path = symbol.file_path

        # 1. Locate AST boundaries
        if not symbol_info:
            try:
                from editing.span_locator import SpanLocator
                locator = SpanLocator()
                region = locator.find_edit_region(symbol.fqn, resolved_path)
                if region:
                    symbol_info = ASTNodeInfo(
                        node_type=symbol.kind or "method",
                        name=symbol.fqn,
                        start_line=region.start_line,
                        end_line=region.end_line,
                        start_byte=region.start_byte,
                        end_byte=region.end_byte,
                        content=region.content
                    )
            except Exception as locator_err:
                logger.warning("[GenericAdapter] SpanLocator error: %s", locator_err)

            if not symbol_info and ast_locator:
                symbol_info = ast_locator.find_symbol(resolved_path, symbol.fqn, original_content)

        if not symbol_info:
            logger.warning(
                "[GenericAdapter] AST locator missed symbol '%s'; using line-range fallback.",
                symbol.fqn,
            )
            lines = original_content.splitlines()
            start_idx = max(0, (symbol.start_line or 1) - 1)
            end_idx = min(len(lines), symbol.end_line or len(lines))
            content_snippet = "\n".join(lines[start_idx:end_idx])
            start_byte = sum(len(l) + 1 for l in lines[:start_idx])
            end_byte = start_byte + len(content_snippet)
            symbol_info = ASTNodeInfo(
                node_type=symbol.kind,
                name=symbol.fqn,
                start_line=symbol.start_line or 1,
                end_line=symbol.end_line or len(lines),
                start_byte=start_byte,
                end_byte=end_byte,
                content=content_snippet,
            )

        # 2. Enhance instruction based on operation type
        instruction = plan.goal
        op = plan.operation
        if op == EditOperation.ADD_METHOD:
            instruction = (
                f"ADD METHOD OPERATION:\n"
                f"Add a new method to this class as described:\n{plan.goal}"
            )
        elif op == EditOperation.DELETE_METHOD:
            instruction = (
                f"DELETE METHOD OPERATION:\n"
                f"Remove the specified method completely:\n{plan.goal}"
            )
        elif op == EditOperation.RENAME_SYMBOL:
            new_name = getattr(plan, "new_name", None) or (plan.extra or {}).get("new_name", "")
            instruction = (
                f"RENAME SYMBOL OPERATION:\n"
                f"Rename this symbol to '{new_name}':\n{plan.goal}"
            )
        elif op == EditOperation.INSERT_STATEMENT:
            anchor = getattr(plan, "anchor", None) or (plan.extra or {}).get("anchor", "")
            position = getattr(plan, "position", "after") or "after"
            instruction = (
                f"INSERT STATEMENT OPERATION:\n"
                f"Insert {position} the line matching '{anchor}':\n{plan.goal}"
            )
        elif op == EditOperation.ADD_ANNOTATION:
            annotation = getattr(plan, "annotation", None) or (plan.extra or {}).get("annotation", "")
            instruction = (
                f"ADD ANNOTATION OPERATION:\n"
                f"Add the annotation '{annotation}' to this symbol:\n{plan.goal}"
            )

        # 3. Build SymbolEditRequest
        from editing.symbol_edit_request import SymbolEditRequest
        edit_req = SymbolEditRequest(
            symbol_id=symbol.symbol_id,
            qualified_name=symbol.fqn,
            current_source=symbol_info.content,
            goal=instruction,
            dependencies=[],
        )

        # 4. Generate patch string via PatchGenerator
        patch_str = ""
        if patch_generator:
            patch_str = patch_generator.generate_patch(
                symbol_info=symbol_info,
                instruction=instruction,
                file_path=resolved_path,
                execution_context=execution_context,
                edit_request=edit_req,
            )

        # 5. Apply search-replace patch string to get new file content
        new_text = original_content
        if patch_applier and patch_str:
            new_text = patch_applier.apply(original_content, patch_str, symbol_info)

        # Parse SEARCH/REPLACE blocks into structured PatchOperation objects
        from editing.patch_engine import PatchOperation, PatchType, PatchSpan
        operations = []
        
        if "<<<<<<< SEARCH" in patch_str:
            parts = patch_str.split("<<<<<<< SEARCH")
            for part in parts[1:]:
                if "=======" not in part or ">>>>>>> REPLACE" not in part:
                    continue
                sub_parts = part.split("=======")
                search_content = sub_parts[0]
                if search_content.startswith("\r\n"):
                    search_content = search_content[2:]
                elif search_content.startswith("\n"):
                    search_content = search_content[1:]
                
                replace_part = sub_parts[1].split(">>>>>>> REPLACE")[0]
                if replace_part.startswith("\r\n"):
                    replace_part = replace_part[2:]
                elif replace_part.startswith("\n"):
                    replace_part = replace_part[1:]
                
                if search_content.endswith("\r\n"):
                    search_content = search_content[:-2]
                elif search_content.endswith("\n"):
                    search_content = search_content[:-1]
                if replace_part.endswith("\r\n"):
                    replace_part = replace_part[:-2]
                elif replace_part.endswith("\n"):
                    replace_part = replace_part[:-1]

                span = PatchSpan(
                    file=symbol.file_path,
                    symbol=symbol.fqn,
                    start_line=symbol_info.start_line,
                    end_line=symbol_info.end_line
                )
                op = PatchOperation(
                    patch_type=PatchType.REPLACE,
                    file=symbol.file_path,
                    start_line=symbol_info.start_line,
                    end_line=symbol_info.end_line,
                    content=replace_part,
                    span=span
                )
                operations.append(op)
        else:
            span = PatchSpan(
                file=symbol.file_path,
                symbol=symbol.fqn,
                start_line=symbol_info.start_line,
                end_line=symbol_info.end_line
            )
            op = PatchOperation(
                patch_type=PatchType.REPLACE,
                file=symbol.file_path,
                start_line=symbol_info.start_line,
                end_line=symbol_info.end_line,
                content=patch_str,
                span=span
            )
            operations.append(op)

        return Patch(
            symbol_fqn=symbol.fqn,
            file_path=symbol.file_path,
            old_text=symbol_info.content,
            new_text=new_text,
            patch_block=patch_str,
            operations=operations,
        )


class JavaAdapter(LanguageAdapter):
    """Java-specific adapter utilizing JavaParser for mature AST symbol location."""

    @property
    def supported_languages(self) -> list[str]:
        return ["java", "kotlin"]

    def build_patch(self, plan: EditPlan, symbol: SymbolHandle, original_content: str, **kwargs) -> Patch:
        logger.debug("[JavaAdapter] Parsing Java/Kotlin file to locate symbol: %s", symbol.fqn)
        
        # 1. Parse content using JavaParser
        from parsers.java_parser import JavaParser
        parser = JavaParser()
        parsed_file = parser.parse(original_content)
        
        matched = None
        target_parts = symbol.fqn.split(".")
        
        # Check methods/constructors
        for m in parsed_file.methods:
            parts = []
            if m.parent:
                parts.append(m.parent)
            parts.append(m.name)
            if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                matched = m
                break
                
        # Check classes
        if not matched:
            for c in parsed_file.classes:
                parts = []
                if c.parent:
                    parts.append(c.parent)
                parts.append(c.name)
                if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                    matched = c
                    break
                    
        # Check interfaces
        if not matched:
            for i in parsed_file.interfaces:
                parts = [i.name]
                if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                    matched = i
                    break
                    
        # Check enums
        if not matched:
            for e in parsed_file.enums:
                parts = [e.name]
                if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                    matched = e
                    break
                    
        symbol_info = None
        if matched and matched.start_byte is not None and matched.end_byte is not None:
            from editing.ast_locator import ASTNodeInfo
            content = original_content.encode("utf-8")[matched.start_byte:matched.end_byte].decode("utf-8", errors="replace")
            symbol_info = ASTNodeInfo(
                node_type=type(matched).__name__.replace("Symbol", "").lower(),
                name=symbol.fqn,
                start_line=matched.line_start,
                end_line=matched.line_end,
                start_byte=matched.start_byte,
                end_byte=matched.end_byte,
                content=content
            )
            logger.info("[JavaAdapter] Surgically located Java symbol %s via AST parsing: lines %d-%d", symbol.fqn, matched.line_start, matched.line_end)
        else:
            logger.warning("[JavaAdapter] Could not surgically locate Java symbol %s via JavaParser; falling back to GenericAdapter", symbol.fqn)

        # Delegate the actual patch building to GenericAdapter, optionally supplying the surgically resolved symbol_info
        return GenericAdapter().build_patch(plan, symbol, original_content, symbol_info=symbol_info, **kwargs)


class PythonAdapter(LanguageAdapter):
    """Python-specific adapter (future home of libcst / ast integration)."""

    @property
    def supported_languages(self) -> list[str]:
        return ["python"]

    def build_patch(self, plan: EditPlan, symbol: SymbolHandle, original_content: str, **kwargs) -> Patch:
        logger.debug("[PythonAdapter] Delegating to GenericAdapter for Python edit.")
        return GenericAdapter().build_patch(plan, symbol, original_content, **kwargs)


class TypeScriptAdapter(LanguageAdapter):
    """TypeScript/JavaScript adapter utilizing TypeScriptParser for mature AST symbol location."""

    @property
    def supported_languages(self) -> list[str]:
        return ["typescript", "javascript"]

    def build_patch(self, plan: EditPlan, symbol: SymbolHandle, original_content: str, **kwargs) -> Patch:
        logger.debug("[TypeScriptAdapter] Parsing TS/JS file to locate symbol: %s", symbol.fqn)
        
        # 1. Parse content using TypeScriptParser
        from parsers.ts_parser import TypeScriptParser
        tsx = symbol.file_path.lower().endswith(".tsx") if symbol.file_path else False
        parser = TypeScriptParser()
        parsed_file = parser.parse(original_content, tsx=tsx)
        
        matched = None
        target_parts = symbol.fqn.split(".")
        
        # Check methods/constructors
        for m in parsed_file.methods:
            parts = []
            if m.parent:
                parts.append(m.parent)
            parts.append(m.name)
            if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                matched = m
                break
                
        # Check functions
        if not matched:
            for f in parsed_file.functions:
                parts = [f.name]
                if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                    matched = f
                    break
                    
        # Check classes
        if not matched:
            for c in parsed_file.classes:
                parts = []
                if c.parent:
                    parts.append(c.parent)
                parts.append(c.name)
                if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                    matched = c
                    break
                    
        # Check interfaces
        if not matched:
            for i in parsed_file.interfaces:
                parts = [i.name]
                if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                    matched = i
                    break
                    
        # Check enums
        if not matched:
            for e in parsed_file.enums:
                parts = [e.name]
                if len(parts) >= len(target_parts) and parts[-len(target_parts):] == target_parts:
                    matched = e
                    break
                    
        symbol_info = None
        if matched and matched.start_byte is not None and matched.end_byte is not None:
            from editing.ast_locator import ASTNodeInfo
            content = original_content.encode("utf-8")[matched.start_byte:matched.end_byte].decode("utf-8", errors="replace")
            symbol_info = ASTNodeInfo(
                node_type=type(matched).__name__.replace("Symbol", "").lower(),
                name=symbol.fqn,
                start_line=matched.line_start,
                end_line=matched.line_end,
                start_byte=matched.start_byte,
                end_byte=matched.end_byte,
                content=content
            )
            logger.info("[TypeScriptAdapter] Surgically located TypeScript symbol %s via AST parsing: lines %d-%d", symbol.fqn, matched.line_start, matched.line_end)
        else:
            logger.warning("[TypeScriptAdapter] Could not surgically locate TypeScript symbol %s via TypeScriptParser; falling back to GenericAdapter", symbol.fqn)

        # Delegate the actual patch building to GenericAdapter, optionally supplying the surgically resolved symbol_info
        return GenericAdapter().build_patch(plan, symbol, original_content, symbol_info=symbol_info, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

_REGISTRY: list[LanguageAdapter] = [
    JavaAdapter(),
    PythonAdapter(),
    TypeScriptAdapter(),
    GenericAdapter(),   # catch-all — must remain last
]


def get_adapter(language: str) -> LanguageAdapter:
    """Return the best adapter for *language*, falling back to :class:`GenericAdapter`."""
    for adapter in _REGISTRY:
        if language in adapter.supported_languages or "*" in adapter.supported_languages:
            return adapter
    return GenericAdapter()
