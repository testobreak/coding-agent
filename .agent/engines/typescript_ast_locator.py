# engines/typescript_ast_locator.py
"""Utility to locate a TypeScript/JavaScript symbol's exact AST span using tree-sitter.

The locator returns line numbers and byte offsets for a fully-qualified symbol name
(e.g., ``UserService.addUser``).
"""

from typing import Tuple
from editing.ast_locator import ASTLocator

class TypeScriptASTLocator:
    """Locate the AST node for a given fully-qualified TypeScript/JavaScript symbol.

    Returns a tuple ``(start_line, end_line, start_byte, end_byte)``.
    Raises ``ValueError`` if the symbol cannot be found.
    """

    def __init__(self):
        self._locator = ASTLocator()

    def locate(self, file_path: str, symbol_fqn: str) -> Tuple[int, int, int, int]:
        node_info = self._locator.find_symbol(file_path, symbol_fqn)
        if not node_info:
            raise ValueError(f"TypeScript symbol {symbol_fqn!r} not found in {file_path}")
        return node_info.start_line, node_info.end_line, node_info.start_byte, node_info.end_byte
