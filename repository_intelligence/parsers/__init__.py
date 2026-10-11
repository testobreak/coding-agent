# repository_intelligence/parsers/__init__.py
from repository_intelligence.parsers.base import SymbolSpanLocator
from repository_intelligence.parsers.python_parser import PythonSymbolLocator
from repository_intelligence.parsers.java_parser import JavaSymbolLocator
from repository_intelligence.parsers.ts_parser import TypeScriptSymbolLocator
import os

def get_parser(file_path: str) -> SymbolSpanLocator:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".java":
        return JavaSymbolLocator()
    elif ext in (".ts", ".tsx"):
        return TypeScriptSymbolLocator()
    return PythonSymbolLocator()
