# repository_intelligence/parsers/java_parser.py
from typing import List, Dict, Optional, Tuple
from repository_intelligence.parsers.base import SymbolSpanLocator
from tree_sitter import Language, Parser
import tree_sitter_java as ts_java

class JavaSymbolLocator(SymbolSpanLocator):
    def __init__(self):
        self.lang = Language(ts_java.language())
        self.parser = Parser(self.lang)

    def extract_symbols(self, file_path: str, source: Optional[str] = None) -> List[Dict]:
        if source is None:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        src_bytes = source.encode("utf-8")
        tree = self.parser.parse(src_bytes)
        symbols = []
        self._traverse(tree.root_node, src_bytes, symbols)
        return symbols

    def _traverse(self, node, src: bytes, symbols: List[Dict]):
        t = node.type
        if t in ("class_declaration", "interface_declaration", "enum_declaration", "method_declaration", "constructor_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace").strip()
                symbols.append({
                    "name": name,
                    "type": t,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1
                })
        for child in node.children:
            self._traverse(child, src, symbols)

    def locate_symbol(self, file_path: str, symbol_name: str, source: Optional[str] = None) -> Optional[Tuple[int, int, int, int]]:
        if source is None:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        src_bytes = source.encode("utf-8")
        tree = self.parser.parse(src_bytes)
        target = symbol_name.split(".")[-1]
        node = self._find_node(tree.root_node, target, src_bytes)
        if node:
            return (node.start_point[0] + 1, node.start_point[1], node.end_point[0] + 1, node.end_point[1])
        return None

    def _find_node(self, node, target: str, src: bytes):
        t = node.type
        if t in ("class_declaration", "interface_declaration", "enum_declaration", "method_declaration", "constructor_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace").strip()
                if name == target:
                    return node
        for child in node.children:
            res = self._find_node(child, target, src)
            if res:
                return res
        return None

    def expand_edit_region(self, file_path: str, start_line: int, end_line: int, source: Optional[str] = None) -> Tuple[int, int]:
        if source is None:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        src_bytes = source.encode("utf-8")
        tree = self.parser.parse(src_bytes)
        node = self._find_node_by_line(tree.root_node, start_line)
        if node:
            start = node.start_point[0] + 1
            curr = node
            while curr.prev_sibling and curr.prev_sibling.type == "annotation":
                curr = curr.prev_sibling
                start = curr.start_point[0] + 1
            end = max(end_line, node.end_point[0] + 1)
            return start, end
        return start_line, end_line

    def _find_node_by_line(self, node, line: int):
        s_line = node.start_point[0] + 1
        e_line = node.end_point[0] + 1
        if s_line <= line <= e_line and node.type in ("class_declaration", "method_declaration", "constructor_declaration"):
            for child in node.children:
                res = self._find_node_by_line(child, line)
                if res:
                    return res
            return node
        for child in node.children:
            res = self._find_node_by_line(child, line)
            if res:
                return res
        return None
