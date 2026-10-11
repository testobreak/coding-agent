# repository_intelligence/parsers/java_type_resolver.py
"""
Mini static type inference for Java code.
Provides a ``TypeResolver`` that can resolve the declared type of a variable
(name) within a file (field, local variable, method parameter) and extract the
base type of generic declarations (e.g. ``JpaRepository<Employee, Long>`` →
``JpaRepository`` with generic args ``["Employee", "Long"]``).

The implementation relies on the existing tree‑sitter Java parser used by
``JavaSymbolLocator``. It walks the syntax tree looking for declaration nodes
and builds a simple per‑file symbol table mapping variable names to their type
strings.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from tree_sitter import Language, Parser
import tree_sitter_java as ts_java


class TypeResolver:
    """Resolve the declared type of a variable in a Java source file.

    The resolver builds a lightweight symbol table for the given file on the
    first call and caches it for subsequent queries.
    """

    def __init__(self) -> None:
        self._parser = Parser(Language(ts_java.language()))
        # Cache mapping file_path -> { variable_name: type_string }
        self._cache: Dict[str, Dict[str, str]] = {}

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def resolve_variable_type(
        self,
        variable_name: str,
        file_path: str,
        source: Optional[str] = None,
    ) -> Optional[str]:
        """Return the declared type of *variable_name* in *file_path*.

        The lookup considers:
        * field declarations (class level)
        * local variable declarations
        * method / constructor parameters
        * generic type arguments (extracted as ``Base<Type1, Type2>``)
        """
        symbol_table = self._get_symbol_table(file_path, source)
        return symbol_table.get(variable_name)

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _get_symbol_table(self, file_path: str, source: Optional[str]) -> Dict[str, str]:
        if file_path in self._cache:
            return self._cache[file_path]

        if source is None:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        src_bytes = source.encode("utf-8")
        tree = self._parser.parse(src_bytes)
        symbols: Dict[str, str] = {}
        self._traverse(tree.root_node, src_bytes, symbols)
        self._cache[file_path] = symbols
        return symbols

    def _traverse(self, node, src: bytes, symbols: Dict[str, str]) -> None:
        """Recursively walk the tree and collect variable -> type mappings.
        """
        t = node.type
        # Field declarations (class level)
        if t == "field_declaration":
            type_node = node.child_by_field_name("type")
            declarator = node.child_by_field_name("declarator")
            if type_node and declarator:
                var_name = self._node_text(declarator, src)
                var_type = self._type_to_string(type_node, src)
                symbols[var_name] = var_type
        # Local variable declarations (e.g. inside a method)
        elif t == "local_variable_declaration":
            type_node = node.child_by_field_name("type")
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node and type_node:
                        var_name = self._node_text(name_node, src)
                        var_type = self._type_to_string(type_node, src)
                        symbols[var_name] = var_type
        # Method / constructor parameters
        elif t == "formal_parameter":
            type_node = node.child_by_field_name("type")
            name_node = node.child_by_field_name("name")
            if type_node and name_node:
                var_name = self._node_text(name_node, src)
                var_type = self._type_to_string(type_node, src)
                symbols[var_name] = var_type
        # Recurse into children
        for child in node.children:
            self._traverse(child, src, symbols)

    def _type_to_string(self, type_node, src: bytes) -> str:
        """Convert a ``type`` node to a readable string, handling generics.
        """
        t = type_node.type
        if t in ("primitive_type", "type_identifier", "scoped_type_identifier"):
            return self._node_text(type_node, src)
        if t == "parameterized_type":
            # Base type identifier
            base_node = type_node.child_by_field_name("type") or type_node.children[0]
            base = self._node_text(base_node, src)
            args_node = type_node.child_by_field_name("type_arguments")
            if args_node:
                args: List[str] = []
                for arg in args_node.children:
                    if arg.type in ("type_identifier", "scoped_type_identifier", "primitive_type"):
                        args.append(self._node_text(arg, src))
                    elif arg.type == "parameterized_type":
                        args.append(self._type_to_string(arg, src))
                return f"{base}<{' , '.join(args)}>".replace(" , ", ", ")
            return base
        return self._node_text(type_node, src)

    def _node_text(self, node, src: bytes) -> str:
        return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()

# End of file
