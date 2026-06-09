# parsers/js_parser.py
#
# Tree-sitter based JavaScript parser.
# Extracts: classes, methods, functions (arrow + regular), imports.
#
# Handles:
#   class Foo { }
#   function bar() { }
#   const baz = () => { }
#   const qux = function() { }
#   import ... from '...'
#   export class / export function
#

from tree_sitter import Language, Parser
import tree_sitter_javascript as ts_js

from parsers.base import (
    ParsedFile, ClassSymbol, MethodSymbol,
    ImportSymbol, node_text
)

_JS_LANG = Language(ts_js.language())
_PARSER = Parser(_JS_LANG)


class JavaScriptParser:

    def parse(self, source: str) -> ParsedFile:
        result = ParsedFile(language="javascript")
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
            return ParsedFile(language="javascript", error=str(e))

    # =========================================================
    # TREE WALK
    # =========================================================

    def _walk(self, node, src: bytes, result: ParsedFile, parent_class: str):
        t = node.type

        # ── Import ──────────────────────────────────────────
        if t == "import_statement":
            text = node_text(node, src).strip()
            result.imports.append(ImportSymbol(
                name=text,
                line_start=node.start_point[0] + 1,
            ))
            return

        # ── Class ───────────────────────────────────────────
        if t == "class_declaration":
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

        # ── Method definition (inside class body) ─────────────
        if t == "method_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                result.methods.append(MethodSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=f"{parent_class}.{name}" if parent_class else name,
                ))
            return

        # ── function_declaration ──────────────────────────────
        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                sym = MethodSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=f"function {name}",
                )
                if parent_class:
                    result.methods.append(sym)
                else:
                    result.functions.append(sym)
                # Recurse into function body
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        self._walk(child, src, result, parent_class=parent_class)
            return

        # ── const foo = () => {} or const foo = function() {} ─
        if t == "lexical_declaration":
            self._extract_variable_fn(node, src, result, parent_class)
            return

        if t == "variable_declaration":
            self._extract_variable_fn(node, src, result, parent_class)
            return

        # ── export_statement — unwrap and recurse ─────────────
        if t == "export_statement":
            for child in node.children:
                self._walk(child, src, result, parent_class=parent_class)
            return

        # ── Default: recurse ─────────────────────────────────
        for child in node.children:
            self._walk(child, src, result, parent_class=parent_class)

    # =========================================================
    # HELPERS
    # =========================================================

    def _extract_variable_fn(self, node, src: bytes, result: ParsedFile, parent_class: str):
        """Handle: const foo = () => {} and const foo = function() {}"""
        for declarator in node.children:
            if declarator.type != "variable_declarator":
                continue
            name_node = declarator.child_by_field_name("name")
            value     = declarator.child_by_field_name("value")
            if not name_node or not value:
                continue
            if value.type not in ("arrow_function", "function", "function_expression"):
                continue
            name = node_text(name_node, src)
            sym = MethodSymbol(
                name=name,
                line_start=declarator.start_point[0] + 1,
                line_end=declarator.end_point[0] + 1,
                parent=parent_class,
                signature=f"const {name} = {value.type}",
            )
            if parent_class:
                result.methods.append(sym)
            else:
                result.functions.append(sym)
