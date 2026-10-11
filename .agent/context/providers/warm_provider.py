# context/providers/warm_provider.py
from dataclasses import dataclass
from typing import List, Any

@dataclass
class WarmContext:
    related_symbols: List[Any]
    imports: List[Any]
    callees: List[Any]

class WarmProvider:
    def __init__(self, state: Any):
        self.state = state

    def resolve(self) -> dict:
        retrieved_symbols = getattr(self.state.working_memory, "retrieved_symbols", []) if getattr(self.state, "working_memory", None) else []
        callers = getattr(self.state.working_memory, "callers", []) if getattr(self.state, "working_memory", None) else []
        callees = getattr(self.state.working_memory, "callees", []) if getattr(self.state, "working_memory", None) else []
        active_symbols = getattr(self.state.runtime_memory, "active_targets", []) if getattr(self.state, "runtime_memory", None) else []
        
        return {
            "retrieved_symbols": retrieved_symbols,
            "callers": callers,
            "callees": callees,
            "active_symbols": active_symbols
        }
