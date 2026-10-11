# engines/patch_engine.py
"""Patch Engine (P1.5)

Provides a surgical edit capability for PATCH mode requests.
It locates the exact edit span using ``PythonASTLocator`` (libcst),
generates the edit via ``SymbolEditor``, validates the resulting code
(syntax, formatting, basic import hygiene), and applies the patch.
"""

from typing import Any, Dict
import ast
import subprocess
import os

# Local utilities
from engines.edit_span import EditSpan
from engines.python_ast_locator import PythonASTLocator

# Import SymbolEditor lazily to avoid circular imports.
def _get_symbol_editor(runtime) -> Any:
    """Create a ``SymbolEditor`` instance using components from the runtime."""
    from editing.symbol_editor import SymbolEditor
    from repository.git_manager import GitManager
    from execution.validators import ExecutionValidator
    from execution.compile_validator import CompileValidator
    from execution.test_runner import TestRunner
    from analysis.impact_analyzer import ImpactAnalyzer
    from retrieval.service import RetrievalFacade

    executor = getattr(runtime, "executor", None)
    
    git_manager = getattr(executor, "git", None)
    if git_manager is None and hasattr(runtime, "file_manager"):
        git_manager = GitManager(runtime.file_manager.root)
        
    validator = getattr(executor, "validator", None)
    if validator is None:
        validator = ExecutionValidator()
        
    compile_validator = getattr(executor, "compile_validator", None)
    if compile_validator is None and hasattr(runtime, "file_manager"):
        compile_validator = CompileValidator(repo_root=runtime.file_manager.root)
        
    test_runner = getattr(executor, "tests", None)
    if test_runner is None and hasattr(runtime, "file_manager"):
        test_runner = TestRunner(runtime.file_manager.root)
        
    impact_analyzer = getattr(executor, "impact_analyzer", None)
    if impact_analyzer is None and hasattr(runtime, "file_manager"):
        impact_analyzer = ImpactAnalyzer(repo_root=runtime.file_manager.root)
        
    retrieval_pipeline = getattr(executor, "retrieval_pipeline", None)
    if retrieval_pipeline is None:
        try:
            retrieval_pipeline = RetrievalFacade().pipeline
        except Exception:
            retrieval_pipeline = None

    return SymbolEditor(
        file_manager=runtime.file_manager,
        state_manager=runtime.state_manager,
        git_manager=git_manager,
        validator=validator,
        compile_validator=compile_validator,
        test_runner=test_runner,
        impact_analyzer=impact_analyzer,
        retrieval_pipeline=retrieval_pipeline,
        llm=runtime.llm,
    )


class PatchEngine:
    """Engine that processes PATCH mode requests.

    Expected request dictionary keys:
        - ``symbol_name``: Fully qualified name of the symbol to edit.
        - ``instruction``: Natural‑language instruction describing the edit.
        - ``file_path`` (optional): Path to the file containing the symbol.
    Returns the result dictionary from ``SymbolEditor.modify`` with an added ``mode`` field.
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self.symbol_editor = _get_symbol_editor(runtime)
        self.ast_locator = PythonASTLocator()

    def run(self, request: Dict[str, Any]) -> Dict[str, Any]:
        symbol_name = request.get("symbol_name")
        instruction = request.get("instruction")
        file_path = request.get("file_path")
        if not symbol_name or not instruction:
            return {
                "success": False,
                "error": "Missing required fields 'symbol_name' or 'instruction' in PATCH request",
                "mode": "PATCH",
            }
        edit_span: EditSpan | None = None
        if file_path:
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".java":
                    from engines.java_ast_locator import JavaASTLocator
                    locator = JavaASTLocator()
                elif ext in (".ts", ".tsx", ".js", ".jsx"):
                    from engines.typescript_ast_locator import TypeScriptASTLocator
                    locator = TypeScriptASTLocator()
                else:
                    locator = self.ast_locator
                start_line, end_line, start_byte, end_byte = locator.locate(file_path, symbol_name)
                edit_span = EditSpan(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    start_byte=start_byte,
                    end_byte=end_byte,
                )
            except Exception:
                edit_span = None
        try:
            result = self.symbol_editor.modify(symbol_name, instruction, file_path=file_path)
            result.setdefault("mode", "PATCH")
            if edit_span:
                result["edit_span"] = edit_span
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "mode": "PATCH"}
