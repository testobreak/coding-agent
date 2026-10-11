# repository_intelligence/parsers/python_parser.py
import ast
from typing import List, Dict, Optional, Tuple
from repository_intelligence.parsers.base import SymbolSpanLocator

class PythonSymbolLocator(SymbolSpanLocator):

    def extract_symbols(self, file_path: str, source: Optional[str] = None) -> List[Dict]:
        if source is None:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()

        symbols = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append({
                        "name": node.name,
                        "type": type(node).__name__,
                        "start_line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno)
                    })
        except Exception:
            pass
        return symbols

    def locate_symbol(self, file_path: str, symbol_name: str, source: Optional[str] = None) -> Optional[Tuple[int, int, int, int]]:
        if source is None:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                    return (node.lineno, node.col_offset, getattr(node, "end_lineno", node.lineno), getattr(node, "end_col_offset", 0))
        except Exception:
            pass
        return None

    def expand_edit_region(self, file_path: str, start_line: int, end_line: int, source: Optional[str] = None) -> Tuple[int, int]:
        return start_line, end_line
