# context/context_package.py
#
# Strongly-typed data models representing structured, compiled context packages
# for reasoning and planning.

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from editing.symbol_handle import SymbolHandle

class ContextRadius(Enum):
    DIRECT = 1
    LOCAL = 2
    EXTENDED = 3

@dataclass
class GoalIntent:
    action: str  # e.g., "modify", "refactor", "add_feature", "analyze", "unknown"
    target: str  # e.g., "EmployeeService"
    domain: str  # e.g., "service", "controller", "repository", "unknown"
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "domain": self.domain,
            "confidence": self.confidence
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoalIntent":
        if not data:
            return None
        return cls(
            action=data.get("action", "unknown"),
            target=data.get("target", "unknown"),
            domain=data.get("domain", "unknown"),
            confidence=data.get("confidence", 0.5)
        )

@dataclass
class ResolvedSymbol:
    name: str
    file_path: str
    symbol_type: str  # e.g., "class", "method", "function", "unknown"
    signature: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None

@dataclass
class Snippet:
    symbol: str
    source: str
    relevance: float

    # Dictionary-like access for backward compatibility
    def __getitem__(self, key: str) -> Any:
        if key == "symbol":
            return self.symbol
        elif key in ("source", "code"):
            return self.source
        elif key == "relevance":
            return self.relevance
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "relevance": self.relevance
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Snippet":
        if not data:
            return None
        return cls(
            symbol=data.get("symbol", ""),
            source=data.get("source", ""),
            relevance=data.get("relevance", 0.0)
        )

@dataclass
class ContextPackage:
    goal: str
    primary_symbol: Optional[SymbolHandle]
    callers: List[SymbolHandle] = field(default_factory=list)
    callees: List[SymbolHandle] = field(default_factory=list)
    related_tests: List[SymbolHandle] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    dependencies: List[SymbolHandle] = field(default_factory=list)
    affected_symbols: List[SymbolHandle] = field(default_factory=list)
    snippets: List[Snippet] = field(default_factory=list)
    risk_score: float = 0.0
    confidence: float = 1.0

    # Extra fields for backward compatibility
    intent: Optional[GoalIntent] = None
    previous_attempts: List[str] = field(default_factory=list)

    # Execution Memory fields
    past_episodes: List[Dict[str, Any]] = field(default_factory=list)
    past_plans: List[Dict[str, Any]] = field(default_factory=list)
    past_repairs: List[Dict[str, Any]] = field(default_factory=list)

    # -------------------------------------------------------------------------
    # Backward Compatibility properties
    # -------------------------------------------------------------------------
    @property
    def target_symbols(self) -> List[ResolvedSymbol]:
        if not self.primary_symbol:
            return []
        name = self.primary_symbol.fqn.split(".")[-1]
        return [ResolvedSymbol(
            name=name,
            file_path=self.primary_symbol.file_path,
            symbol_type=self.primary_symbol.kind,
            start_line=self.primary_symbol.start_line,
            end_line=self.primary_symbol.end_line
        )]

    @property
    def related_symbols(self) -> List[ResolvedSymbol]:
        res = []
        for sym in self.callers + self.callees + self.dependencies:
            name = sym.fqn.split(".")[-1]
            res.append(ResolvedSymbol(
                name=name,
                file_path=sym.file_path,
                symbol_type=sym.kind,
                start_line=sym.start_line,
                end_line=sym.end_line
            ))
        return res

    @property
    def related_files(self) -> List[str]:
        files = set()
        if self.primary_symbol and self.primary_symbol.file_path:
            files.add(self.primary_symbol.file_path)
        for sym in self.callers + self.callees + self.dependencies + self.related_tests + self.affected_symbols:
            if sym.file_path:
                files.add(sym.file_path)
        return list(files)

    @property
    def tests(self) -> List[Dict[str, Any]]:
        res = []
        for t in self.related_tests:
            res.append({
                "name": t.fqn,
                "file_path": t.file_path,
                "type": "unit_test"
            })
        return res

    @property
    def dependency_graph(self) -> List[Dict[str, Any]]:
        res = []
        p_name = self.primary_symbol.fqn.split(".")[-1] if self.primary_symbol else "unknown"
        for c in self.callers:
            c_name = c.fqn.split(".")[-1]
            res.append({"source": c_name, "target": p_name, "type": "CALLS", "confidence": 1.0})
        for c in self.callees:
            c_name = c.fqn.split(".")[-1]
            res.append({"source": p_name, "target": c_name, "type": "CALLS", "confidence": 1.0})
        return res

    @property
    def architectural_summary(self) -> str:
        # Compatibility property to satisfy verify_context_builder.py
        summary = "Architectural constraints:\n- Preserve existing codebase architecture and design patterns.\n"
        if self.primary_symbol:
            summary += f"\nTarget Symbol(s): {self.primary_symbol.fqn.split('.')[-1]} is the primary target context."
        return summary

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "primary_symbol": self.primary_symbol.to_dict() if self.primary_symbol else None,
            "callers": [c.to_dict() for c in self.callers],
            "callees": [c.to_dict() for c in self.callees],
            "related_tests": [t.to_dict() for t in self.related_tests],
            "imports": self.imports,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "affected_symbols": [a.to_dict() for a in self.affected_symbols],
            "snippets": [s.to_dict() for s in self.snippets],
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "intent": self.intent.to_dict() if self.intent else None,
            "previous_attempts": self.previous_attempts,
            "past_episodes": self.past_episodes,
            "past_plans": self.past_plans,
            "past_repairs": self.past_repairs
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextPackage":
        if not data:
            return None
        return cls(
            goal=data.get("goal", ""),
            primary_symbol=SymbolHandle.from_dict(data.get("primary_symbol")),
            callers=[SymbolHandle.from_dict(c) for c in data.get("callers", [])],
            callees=[SymbolHandle.from_dict(c) for c in data.get("callees", [])],
            related_tests=[SymbolHandle.from_dict(t) for t in data.get("related_tests", [])],
            imports=data.get("imports", []),
            dependencies=[SymbolHandle.from_dict(d) for d in data.get("dependencies", [])],
            affected_symbols=[SymbolHandle.from_dict(a) for a in data.get("affected_symbols", [])],
            snippets=[Snippet.from_dict(s) for s in data.get("snippets", [])],
            risk_score=data.get("risk_score", 0.0),
            confidence=data.get("confidence", 1.0),
            intent=GoalIntent.from_dict(data.get("intent")),
            previous_attempts=data.get("previous_attempts", []),
            past_episodes=data.get("past_episodes", []),
            past_plans=data.get("past_plans", []),
            past_repairs=data.get("past_repairs", [])
        )
