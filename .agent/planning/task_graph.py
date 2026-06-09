# planning/task_graph.py

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class SymbolRef:
    symbol_id: Optional[str] = None
    symbol_name: Optional[str] = None
    file_id: Optional[str] = None
    repository_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "symbol_name": self.symbol_name,
            "file_id": self.file_id,
            "repository_id": self.repository_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SymbolRef":
        if not data:
            return cls()
        return cls(
            symbol_id=data.get("symbol_id"),
            symbol_name=data.get("symbol_name"),
            file_id=data.get("file_id"),
            repository_id=data.get("repository_id")
        )

@dataclass
class DependencyEdge:
    source: str
    target: str
    edge_type: str = "dependency"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyEdge":
        return cls(
            source=data["source"],
            target=data["target"],
            edge_type=data.get("edge_type", "dependency")
        )

@dataclass
class TaskGraph:
    graph_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    nodes: Dict[str, Any] = field(default_factory=dict)  # Stores TaskNode objects
    edges: List[DependencyEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: Any):
        self.nodes[node.id] = node

    def add_edge(self, source: str, target: str, edge_type: str = "dependency"):
        self.edges.append(DependencyEdge(source=source, target=target, edge_type=edge_type))
        # Ensure target node updates its dependencies
        if target in self.nodes:
            if source not in self.nodes[target].dependencies:
                self.nodes[target].dependencies.append(source)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "nodes": {nid: n.to_dict() if hasattr(n, "to_dict") else n for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskGraph":
        from planning.task_node import TaskNode
        if not data:
            return cls()
        
        nodes = {}
        for nid, n_dict in data.get("nodes", {}).items():
            nodes[nid] = TaskNode.from_dict(n_dict)
            
        edges = [DependencyEdge.from_dict(e) for e in data.get("edges", [])]
        return cls(
            graph_id=data.get("graph_id", str(uuid.uuid4())),
            nodes=nodes,
            edges=edges,
            metadata=data.get("metadata", {})
        )
