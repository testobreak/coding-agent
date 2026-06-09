# parsers/java_parser.py
#
# Tree-sitter based Java parser.
# Extracts: classes, interfaces, enums, methods, constructors, imports.
#
# Handles:
#   - top-level classes
#   - nested / inner classes
#   - anonymous classes (skipped — no name)
#   - generic classes (captures base name)
#   - interface declarations
#   - enum declarations
#   - method declarations
#   - constructor declarations
#   - import declarations
#

from tree_sitter import Language, Parser
import tree_sitter_java as ts_java

from parsers.base import (
    ParsedFile, ClassSymbol, MethodSymbol,
    InterfaceSymbol, EnumSymbol, ImportSymbol, node_text
)

_JAVA_LANG = Language(ts_java.language())
_PARSER = Parser(_JAVA_LANG)


class JavaParser:

    def parse(self, source: str) -> ParsedFile:
        result = ParsedFile(language="java")
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
            return ParsedFile(language="java", error=str(e))

    # =========================================================
    # TREE WALK
    # =========================================================

    def _walk(self, node, src: bytes, result: ParsedFile, parent_class: str):
        t = node.type

        # ── Import ──────────────────────────────────────────
        if t == "import_declaration":
            name = node_text(node, src).strip().rstrip(";").replace("import ", "").strip()
            result.imports.append(ImportSymbol(name=name, line_start=node.start_point[0] + 1))
            return  # no children worth descending

        # ── Class ───────────────────────────────────────────
        if t == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                sym  = ClassSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=self._class_signature(node, src),
                )
                result.classes.append(sym)
                # Recurse into class body using this class as parent
                for child in node.children:
                    self._walk(child, src, result, parent_class=name)
                return

        # ── Interface ────────────────────────────────────────
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
                for child in node.children:
                    self._walk(child, src, result, parent_class=name)
                return

        # ── Enum ─────────────────────────────────────────────
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
                for child in node.children:
                    self._walk(child, src, result, parent_class=name)
                return

        # ── Method ───────────────────────────────────────────
        if t == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                result.methods.append(MethodSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=self._method_signature(node, src),
                ))
            # Don't descend further — inner classes inside method bodies are rare
            return

        # ── Constructor ──────────────────────────────────────
        if t == "constructor_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = node_text(name_node, src)
                result.methods.append(MethodSymbol(
                    name=name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_class,
                    signature=f"{name}(constructor)",
                ))
            return

        # ── Default: recurse ─────────────────────────────────
        for child in node.children:
            self._walk(child, src, result, parent_class=parent_class)

    # =========================================================
    # SIGNATURE HELPERS
    # =========================================================

    def _class_signature(self, node, src: bytes) -> str:
        """Build a short readable signature: 'public class EmployeeService'."""
        parts = []
        for child in node.children:
            if child.type in ("modifiers",):
                parts.append(node_text(child, src))
            elif child.type == "class":
                parts.append("class")
            elif child.type == "identifier":
                parts.append(node_text(child, src))
                break
        return " ".join(parts)

    def _method_signature(self, node, src: bytes) -> str:
        """Build: 'public Employee createEmployee(String name)'."""
        parts = []
        for child in node.children:
            if child.type == "block":
                break  # stop before method body
            parts.append(node_text(child, src).strip())
        return " ".join(p for p in parts if p)
