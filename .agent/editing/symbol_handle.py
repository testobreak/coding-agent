# editing/symbol_handle.py
#
# SymbolHandle model representing a uniquely addressable symbol in the codebase.

from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class SymbolHandle:
    symbol_id: str
    fqn: str          # fully qualified name, e.g. EmployeeService.saveEmployee
    kind: str         # e.g., "class", "method", "function", "fallback"
    file_path: str
    start_line: int
    end_line: int
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "fqn": self.fqn,
            "kind": self.kind,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "confidence": self.confidence
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolHandle":
        if not data:
            return None
        return cls(
            symbol_id=data.get("symbol_id", ""),
            fqn=data.get("fqn", ""),
            kind=data.get("kind", "unknown"),
            file_path=data.get("file_path", ""),
            start_line=data.get("start_line", 1),
            end_line=data.get("end_line", 1),
            confidence=data.get("confidence", 1.0)
        )

