# context/snippet_builder.py
#
# Snippet Extraction logic. Parses boundary line ranges from resolved symbol scopes
# to avoid full-file imports and minimize LLM context package footprint.

import os
from typing import List, Dict, Any
from context.context_package import ResolvedSymbol

class SnippetBuilder:
    def build_snippets(self, target_symbols: List[ResolvedSymbol], repo_root: str) -> List[Dict[str, Any]]:
        snippets = []
        for sym in target_symbols:
            if not sym.file_path:
                continue
            
            abs_path = os.path.join(repo_root, sym.file_path)
            if not os.path.exists(abs_path):
                abs_path = sym.file_path if os.path.isabs(sym.file_path) else os.path.abspath(sym.file_path)
                if not os.path.exists(abs_path):
                    continue
            
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Pick snippet boundaries
                start = max(1, sym.start_line or 1)
                end = min(len(lines), sym.end_line or len(lines))
                
                # Extract surrounding context (e.g. 5 lines before and after)
                start_idx = max(0, start - 6)
                end_idx = min(len(lines), end + 5)
                
                content = "".join(lines[start_idx:end_idx])
                snippets.append({
                    "symbol": sym.name,
                    "file_path": sym.file_path,
                    "start_line": start_idx + 1,
                    "end_line": end_idx,
                    "code": content
                })
            except Exception as e:
                print(f"[SnippetBuilder] Warning: Failed reading snippet for {sym.name} in {sym.file_path}: {e}")
                
        return snippets
