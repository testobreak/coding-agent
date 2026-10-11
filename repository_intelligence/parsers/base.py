# repository_intelligence/parsers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple

class SymbolSpanLocator(ABC):

    @abstractmethod
    def extract_symbols(self, file_path: str, source: Optional[str] = None) -> List[Dict]:
        """Extract all symbols in the file. Returns a list of dictionaries with metadata."""
        pass

    @abstractmethod
    def locate_symbol(self, file_path: str, symbol_name: str, source: Optional[str] = None) -> Optional[Tuple[int, int, int, int]]:
        """Locate start_line, start_col, end_line, end_col of a symbol."""
        pass

    @abstractmethod
    def expand_edit_region(self, file_path: str, start_line: int, end_line: int, source: Optional[str] = None) -> Tuple[int, int]:
        """Expand the edit region around the lines to capture complete logical scopes (like annotations, methods, etc.)."""
        pass
