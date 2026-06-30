# editing/symbol_resolver.py
#
# Resolves a string symbol identifier into one or more SymbolHandle objects.

import os
from typing import List

class SymbolResolutionError(Exception):
    pass
from context.symbol_resolver import SymbolResolver as ContextResolver
from editing.symbol_handle import SymbolHandle

class SymbolResolver:
    def __init__(self, db_session=None):
        self._inner = ContextResolver()
        self.db_session = db_session

    def resolve(self, symbol_name: str, file_path: str = None) -> List[SymbolHandle]:
        """
        Resolves the symbol name. If not found in DB, builds a fallback SymbolHandle if file_path exists.
        """
        resolved_symbols = self._inner.resolve(symbol_name, session=self.db_session)
        
        # Filter by file path if provided
        if file_path and resolved_symbols:
            filtered = [s for s in resolved_symbols if s.file_path == file_path]
            if filtered:
                resolved_symbols = filtered
                
        handles = []
        for i, s in enumerate(resolved_symbols):
            handles.append(SymbolHandle(
                symbol_id=f"sym_{i}_{s.name}",
                fqn=symbol_name,
                kind=s.symbol_type or "unknown",
                file_path=s.file_path,
                start_line=s.start_line if s.start_line is not None else 1,
                end_line=s.end_line if s.end_line is not None else 1
            ))
            
        # Build fallback handle if no symbols were resolved from database but file_path exists
        if not handles and file_path:
            full_path = os.path.abspath(os.path.join("/Users/ashish/Downloads/HRMS", file_path))
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        lines_count = len(f.read().splitlines()) or 1
                except Exception:
                    lines_count = 1
                    
                handles.append(SymbolHandle(
                    symbol_id=f"sym_fallback_{symbol_name}",
                    fqn=symbol_name,
                    kind="fallback",
                    file_path=file_path,
                    start_line=1,
                    end_line=lines_count
                ))
                
        return handles
