# parsers/python_parser.py
#
# Tree-sitter based Python parser.
# Extracts: classes, methods (inside classes), top-level functions, imports.
#

from tree_sitter import Language, Parser
import tree_sitter_python as ts_python

from parsers.base import (
    ParsedFile, ClassSymbol, MethodSymbol,
    ImportSymbol, node_text
)

_PY_LANG = Language(ts_python.language())
_PARSER = Parser(_PY_LANG)


class PythonParser:

    def parse(self, source: str) -> ParsedFile:
        result = ParsedFile(language="python")
        try:
            src_bytes = source.encode("utf-8")
            tree = _PARSER.parse(src_bytes)
            self._walk(tree.root_node, src_bytes, result, parent_class=None)
        except Exception as e:
            result.error = str(e)
        return result

    def parse_file(self, path: str) -> ParsedFile:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return self.parse(f.read())
        except OSError as e:
            return ParsedFile(language="python", error=str(e))

    # =========================================================
    # TREE WALK
    # =========================================================

    def _walk(self, node, src: bytes, result: ParsedFile, parent_class: str):
        t = node.type

        # ── Import ──────────────────────────────────────────
        if t in ("import_statement", "import_from_statement"):
            text = node_text(node, src).strip()
            result.imports.append(ImportSymbol(
                name=text,
                line_start=node.start_point[0] + 1,
            ))
            return

        # ── Class definition ─────────────────────────────────
        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                result.classes.append(ClassSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=f"class {name}",
                ))
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        self._walk(child, src, result, parent_class=name)
            return

        # ── Function / method definition ──────────────────────
        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                params = node.child_by_field_name("parameters")
                sig = f"def {name}{node_text(params, src) if params else '()'}"

                sym = MethodSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=sig,
                )
                if parent_class:
                    result.methods.append(sym)
                else:
                    result.functions.append(sym)

                # Recurse — nested functions / classes inside function
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        self._walk(child, src, result, parent_class=parent_class)
            return

        # ── Default: recurse ─────────────────────────────────
        for child in node.children:
            self._walk(child, src, result, parent_class=parent_class)
