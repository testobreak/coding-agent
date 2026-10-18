# repository_intelligence/parsers/__init__.py
from repository_intelligence.parsers.base import SymbolSpanLocator
from repository_intelligence.parsers.python_parser import PythonSymbolLocator

try:
    from repository_intelligence.parsers.java_parser import JavaSymbolLocator
except ImportError:
    JavaSymbolLocator = None

try:
    from repository_intelligence.parsers.ts_parser import TypeScriptSymbolLocator
except ImportError:
    TypeScriptSymbolLocator = None

import os

def get_parser(file_path: str) -> SymbolSpanLocator:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".java":
        if JavaSymbolLocator is None:
            raise ImportError("tree_sitter is required for Java parsing")
        return JavaSymbolLocator()
    elif ext in (".ts", ".tsx"):
        if TypeScriptSymbolLocator is None:
            raise ImportError("tree_sitter is required for TypeScript parsing")
        return TypeScriptSymbolLocator()
    return PythonSymbolLocator()
