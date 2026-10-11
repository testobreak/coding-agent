# repository_intelligence/symbol_locator.py
import json
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class SymbolSpan:
    symbol_name: str
    file_path: str
    start_line: int
    end_line: int
    symbol_type: str
    parent_symbol: str | None = None

class SymbolLocator:
    def __init__(self):
        self.repo_root = os.getcwd()
        if os.path.basename(self.repo_root) == ".agent":
            self.repo_root = os.path.dirname(self.repo_root)
        
        self.index_path = os.path.join(self.repo_root, ".agent", "repository", "symbol_index.json")
        self.symbols_cache = {}
        self._load_index()

    def _load_index(self):
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    self.symbols_cache = json.load(f)
            except Exception as e:
                print(f"[SymbolLocator] Error loading symbol_index.json: {e}")

    def locate(self, symbol_query: str, active_file: Optional[str] = None, related_files: list[str] = []) -> Optional[SymbolSpan]:
        if not symbol_query:
            return None

        # 1️⃣ Exact match lookup
        if symbol_query in self.symbols_cache:
            entry = self.symbols_cache[symbol_query]
            return self._build_span_with_ast_rescan(symbol_query, entry)

        # 2️⃣ Suffix / Qualified fallback matching
        matches = []
        query_suffix = f".{symbol_query}"
        for key, entry in self.symbols_cache.items():
            if key == symbol_query or key.endswith(query_suffix):
                matches.append((key, entry))

        if not matches:
            return None

        # 3️⃣ Rank multiple matches (active file gets massive priority)
        best_match = None
        best_score = -1.0
        
        for key, entry in matches:
            score = 0.0
            
            # Active file bonus
            if active_file:
                # Normalize paths
                rel_active = os.path.relpath(active_file, self.repo_root) if os.path.isabs(active_file) else active_file
                rel_entry = entry["file_path"]
                if rel_active == rel_entry or os.path.basename(rel_active) == os.path.basename(rel_entry):
                    score += 5.0
            
            # Related files proximity
            for ref in related_files:
                rel_ref = os.path.relpath(ref, self.repo_root) if os.path.isabs(ref) else ref
                if rel_ref == entry["file_path"]:
                    score += 3.0
                    
            if score > best_score:
                best_score = score
                best_match = (key, entry)

        if best_match:
            key, entry = best_match
            return self._build_span_with_ast_rescan(key, entry)
            
        return None

    def _build_span_with_ast_rescan(self, symbol_name: str, entry: dict) -> SymbolSpan:
        """Create a SymbolSpan, automatically rescanning the file using language-specific AST
        parsers if the index might be stale.
        """
        abs_path = os.path.join(self.repo_root, entry["file_path"])
        start_line = entry["start_line"]
        end_line = entry["end_line"]

        # Run AST rescan as a safety fallback to locate exact current boundaries
        if os.path.exists(abs_path):
            parsed_file = None
            try:
                if abs_path.endswith(".py"):
                    from parsers.python_parser import PythonParser
                    parsed_file = PythonParser().parse_file(abs_path)
                elif abs_path.endswith(".java"):
                    from parsers.java_parser import JavaParser
                    parsed_file = JavaParser().parse_file(abs_path)
                elif abs_path.endswith(".ts") or abs_path.endswith(".tsx"):
                    from parsers.ts_parser import TypeScriptParser
                    parsed_file = TypeScriptParser().parse_file(abs_path)
                elif abs_path.endswith(".js") or abs_path.endswith(".jsx"):
                    from parsers.js_parser import JavaScriptParser
                    parsed_file = JavaScriptParser().parse_file(abs_path)
            except Exception:
                pass

            if parsed_file and not parsed_file.error:
                all_symbols = (
                    parsed_file.classes + parsed_file.methods + 
                    parsed_file.interfaces + parsed_file.enums + 
                    parsed_file.functions
                )
                
                # Check for matching symbol name
                short_name = symbol_name.split(".")[-1]
                for sym in all_symbols:
                    if sym.name == short_name:
                        start_line = sym.line_start
                        end_line = sym.line_end
                        break

        return SymbolSpan(
            symbol_name=symbol_name,
            file_path=abs_path,
            start_line=start_line,
            end_line=end_line,
            symbol_type=entry["type"],
            parent_symbol=entry.get("parent")
        )
