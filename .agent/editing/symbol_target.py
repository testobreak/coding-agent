# editing/symbol_target.py
#
# First-class SymbolTarget primitive representing a resolved symbol to be modified.

from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class SymbolTarget:
    symbol_id: str
    qualified_name: str
    symbol_type: str  # e.g., "class", "method", "function", "fallback"
    file_path: str
    start_line: int
    end_line: int
    parent_symbol: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "qualified_name": self.qualified_name,
            "symbol_type": self.symbol_type,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent_symbol": self.parent_symbol
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolTarget":
        if not data:
            return None
        return cls(
            symbol_id=data.get("symbol_id", ""),
            qualified_name=data.get("qualified_name", ""),
            symbol_type=data.get("symbol_type", "unknown"),
            file_path=data.get("file_path", ""),
            start_line=data.get("start_line", 1),
            end_line=data.get("end_line", 1),
            parent_symbol=data.get("parent_symbol")
        )
