# editing/symbol_edit_request.py
#
# Structured edit request object encapsulating target, current code, goal, and dependency context.

from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class SymbolEditRequest:
    symbol_id: str
    qualified_name: str
    current_source: str
    goal: str
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "qualified_name": self.qualified_name,
            "current_source": self.current_source,
            "goal": self.goal,
            "dependencies": self.dependencies
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolEditRequest":
        if not data:
            return None
        return cls(
            symbol_id=data.get("symbol_id", ""),
            qualified_name=data.get("qualified_name", ""),
            current_source=data.get("current_source", ""),
            goal=data.get("goal", ""),
            dependencies=data.get("dependencies", [])
        )
