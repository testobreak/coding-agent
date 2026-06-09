# parsers/ts_parser.py
#
# Tree-sitter based TypeScript parser.
# Reuses the JS parser logic but with the TypeScript grammar.
# Also extracts TypeScript-specific constructs:
#   interface declarations
#   enum declarations
#   type alias declarations (stored as CLASS with type="TYPE_ALIAS")
#

from tree_sitter import Language, Parser
import tree_sitter_typescript as ts_typescript

from parsers.base import (
    ParsedFile, ClassSymbol, MethodSymbol,
    InterfaceSymbol, EnumSymbol, ImportSymbol, node_text
)

# tree-sitter-typescript exposes two grammars: typescript and tsx
_TS_LANG  = Language(ts_typescript.language_typescript())
_TSX_LANG = Language(ts_typescript.language_tsx())

_TS_PARSER = Parser(_TS_LANG)

_TSX_PARSER = Parser(_TSX_LANG)


class TypeScriptParser:

    def parse(self, source: str, tsx: bool = False) -> ParsedFile:
        result = ParsedFile(language="tsx" if tsx else "typescript")
        try:
            src_bytes = source.encode("utf-8")
            parser = _TSX_PARSER if tsx else _TS_PARSER
            tree = parser.parse(src_bytes)
            self._walk(tree.root_node, src_bytes, result, parent_class=None)
        except Exception as e:
            result.error = str(e)
        return result

    def parse_file(self, path: str) -> ParsedFile:
        tsx = path.lower().endswith(".tsx")
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return self.parse(f.read(), tsx=tsx)
        except OSError as e:
            lang = "tsx" if tsx else "typescript"
            return ParsedFile(language=lang, error=str(e))

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

        # ── Interface (TS-specific) ───────────────────────────
        if t == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                result.interfaces.append(InterfaceSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    signature=f"interface {name}",
                ))
                # Recurse into interface body for method signatures
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        self._walk(child, src, result, parent_class=name)
            return

        # ── Enum (TS-specific) ────────────────────────────────
        if t == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                result.enums.append(EnumSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    signature=f"enum {name}",
                ))
            return

        # ── Type alias (TS-specific) — store as pseudo-class ──
        if t == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                result.classes.append(ClassSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=f"type {name}",
                ))
            return

        # ── Method definition ─────────────────────────────────
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

        # ── method_signature (inside interface) ───────────────
        if t == "method_signature":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                result.methods.append(MethodSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=node_text(node, src).strip(),
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
            return

        # ── const/let arrow functions ─────────────────────────
        if t in ("lexical_declaration", "variable_declaration"):
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
