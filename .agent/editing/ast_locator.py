# editing/ast_locator.py
#
# Locates a symbol's exact AST node, start/end lines, and byte offsets.

import os
from dataclasses import dataclass
from tree_sitter import Language, Parser
import tree_sitter_java as ts_java
import tree_sitter_python as ts_python
import tree_sitter_javascript as ts_js
import tree_sitter_typescript as ts_typescript

@dataclass
class ASTNodeInfo:
    node_type: str
    name: str
    start_line: int  # 1-indexed
    end_line: int    # 1-indexed
    start_byte: int
    end_byte: int
    content: str

class ASTLocator:
    def __init__(self):
        # Initialize languages
        self.langs = {
            "java": Language(ts_java.language()),
            "python": Language(ts_python.language()),
            "javascript": Language(ts_js.language()),
            "typescript": Language(ts_typescript.language_typescript()),
            "tsx": Language(ts_typescript.language_tsx())
        }
        
    def get_language(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".java":
            return "java"
        elif ext == ".py":
            return "python"
        elif ext == ".js" or ext == ".jsx":
            return "javascript"
        elif ext == ".ts":
            return "typescript"
        elif ext == ".tsx":
            return "tsx"
        return "unknown"

    def find_symbol(self, file_path: str, symbol_name: str, source: str = None) -> ASTNodeInfo | None:
        if source is None:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
                
        lang_str = self.get_language(file_path)
        lang = self.langs.get(lang_str)
        if not lang:
            # Fallback text block matcher if language not supported
            return self._fallback_match(source, symbol_name)

        parser = Parser(lang)
        src_bytes = source.encode("utf-8")
        tree = parser.parse(src_bytes)
        
        # Search the tree for nodes matching the symbol_name
        target_parts = symbol_name.split(".")
        
        found_node = self._find_matching_node(tree.root_node, target_parts, src_bytes)
        if found_node:
            start_line = found_node.start_point[0] + 1
            end_line = found_node.end_point[0] + 1
            content = src_bytes[found_node.start_byte:found_node.end_byte].decode("utf-8", errors="replace")
            return ASTNodeInfo(
                node_type=found_node.type,
                name=symbol_name,
                start_line=start_line,
                end_line=end_line,
                start_byte=found_node.start_byte,
                end_byte=found_node.end_byte,
                content=content
            )
        
        # Fallback suffix/substring matching if hierarchical matching failed
        found_node = self._find_any_matching_node(tree.root_node, target_parts[-1], src_bytes)
        if found_node:
            start_line = found_node.start_point[0] + 1
            end_line = found_node.end_point[0] + 1
            content = src_bytes[found_node.start_byte:found_node.end_byte].decode("utf-8", errors="replace")
            return ASTNodeInfo(
                node_type=found_node.type,
                name=symbol_name,
                start_line=start_line,
                end_line=end_line,
                start_byte=found_node.start_byte,
                end_byte=found_node.end_byte,
                content=content
            )
            
        return None

    def _get_node_name(self, node, src: bytes) -> str | None:
        t = node.type
        name_node = None
        if t in ("class_declaration", "class_definition", "interface_declaration", "enum_declaration", "method_declaration", "method_definition", "function_declaration", "function_definition", "constructor_declaration"):
            name_node = node.child_by_field_name("name")
        elif t == "variable_declarator":
            name_node = node.child_by_field_name("name")
        
        if name_node:
            return src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace").strip()
        return None

    def _find_matching_node(self, node, target_parts: list[str], src: bytes, current_path: list[str] = None):
        if current_path is None:
            current_path = []
            
        # Get node name
        node_name = self._get_node_name(node, src)
        new_path = current_path
        if node_name:
            new_path = current_path + [node_name]
            if len(new_path) >= len(target_parts):
                if new_path[-len(target_parts):] == target_parts:
                    return node

        # Recurse children
        for child in node.children:
            res = self._find_matching_node(child, target_parts, src, new_path)
            if res:
                return res
        return None

    def _find_any_matching_node(self, node, short_name: str, src: bytes):
        node_name = self._get_node_name(node, src)
        if node_name == short_name:
            return node
        for child in node.children:
            res = self._find_any_matching_node(child, short_name, src)
            if res:
                return res
        return None

    def _fallback_match(self, source: str, symbol_name: str) -> ASTNodeInfo | None:
        lines = source.splitlines()
        target = symbol_name.split(".")[-1]
        for i, line in enumerate(lines):
            if target in line:
                start_line = i + 1
                start_byte = sum(len(l) + 1 for l in lines[:i])
                end_byte = start_byte + len(line)
                return ASTNodeInfo(
                    node_type="fallback",
                    name=symbol_name,
                    start_line=start_line,
                    end_line=start_line,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    content=line
                )
        return None
