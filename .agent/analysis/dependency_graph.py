import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.file import File
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.symbol import Symbol, SymbolRelationship


GRAPH_CACHE = ".cache/dependency_graph.json"


class DependencyGraph:

    def __init__(self):

        self.edges: Dict[str, List[str]] = defaultdict(list)
        self.reverse: Dict[str, List[str]] = defaultdict(list)
        self.file_edges: Dict[str, List[str]] = defaultdict(list)
        self.file_reverse: Dict[str, List[str]] = defaultdict(list)
        self._built = False

    def build(
        self,
        chunks: List[dict] = None,
        repo_root: str = "."
    ) -> None:

        self.edges = defaultdict(list)
        self.reverse = defaultdict(list)
        self.file_edges = defaultdict(list)
        self.file_reverse = defaultdict(list)

        root_path = str(Path(repo_root).resolve())
        print("[DependencyGraph] Building symbol relationship graph...")

        session = SessionLocal()

        try:
            repository = (
                session.query(Repository)
                .filter(Repository.root_path == root_path)
                .one_or_none()
            )

            if not repository:
                self._built = True
                print("[DependencyGraph] No repository index found.")
                return

            source_file = File.__table__.alias("source_file")
            target_symbol = Symbol.__table__.alias("target_symbol")
            target_file = File.__table__.alias("target_file")

            rows = (
                session.query(
                    Symbol.qualified_name.label("source_symbol"),
                    source_file.c.path.label("source_file"),
                    target_symbol.c.qualified_name.label("target_symbol"),
                    target_file.c.path.label("target_file")
                )
                .select_from(SymbolRelationship)
                .outerjoin(
                    Symbol,
                    SymbolRelationship.source_symbol_id == Symbol.id
                )
                .outerjoin(
                    source_file,
                    Symbol.file_id == source_file.c.id
                )
                .outerjoin(
                    target_symbol,
                    SymbolRelationship.target_symbol_id == target_symbol.c.id
                )
                .outerjoin(
                    target_file,
                    target_symbol.c.file_id == target_file.c.id
                )
                .filter(
                    SymbolRelationship.repository_id == repository.id
                )
                .all()
            )

            for row in rows:
                if row.source_symbol and row.target_symbol:
                    self.edges[row.source_symbol].append(row.target_symbol)
                    self.reverse[row.target_symbol].append(row.source_symbol)

                if (
                    row.source_file
                    and row.target_file
                    and row.source_file != row.target_file
                ):
                    self.file_edges[row.source_file].append(row.target_file)
                    self.file_reverse[row.target_file].append(row.source_file)

        finally:
            session.close()

        self.edges = self._dedupe(self.edges)
        self.reverse = self._dedupe(self.reverse)
        self.file_edges = self._dedupe(self.file_edges)
        self.file_reverse = self._dedupe(self.file_reverse)
        self._built = True

        print(
            f"[DependencyGraph] Built: {len(self.edges)} symbols, "
            f"{sum(len(v) for v in self.edges.values())} edges."
        )

    def dependencies_of(
        self,
        file_path: str,
        depth: int = 1
    ) -> List[str]:

        return self._bfs(
            self.file_edges,
            file_path,
            depth
        )

    def dependents_of(
        self,
        file_path: str,
        depth: int = 1
    ) -> List[str]:

        return self._bfs(
            self.file_reverse,
            file_path,
            depth
        )

    def neighborhood(
        self,
        file_path: str,
        depth: int = 1
    ) -> List[str]:

        deps = set(
            self.dependencies_of(file_path, depth)
        )
        rdeps = set(
            self.dependents_of(file_path, depth)
        )
        result = deps | rdeps
        result.discard(file_path)

        return list(result)

    def related_symbols(
        self,
        qualified_name: str,
        depth: int = 1
    ) -> List[str]:

        return self._bfs(
            self.edges,
            qualified_name,
            depth
        )

    def incoming_symbols(
        self,
        qualified_name: str,
        depth: int = 1
    ) -> List[str]:

        return self._bfs(
            self.reverse,
            qualified_name,
            depth
        )

    def save(self) -> None:

        os.makedirs(
            os.path.dirname(GRAPH_CACHE),
            exist_ok=True
        )

        with open(GRAPH_CACHE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "edges": dict(self.edges),
                    "reverse": dict(self.reverse),
                    "file_edges": dict(self.file_edges),
                    "file_reverse": dict(self.file_reverse)
                },
                f,
                indent=2
            )

        print(f"[DependencyGraph] Saved to {GRAPH_CACHE}")

    def load(self) -> bool:

        if not os.path.exists(GRAPH_CACHE):
            return False

        try:
            with open(GRAPH_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.edges = defaultdict(list, data.get("edges", {}))
            self.reverse = defaultdict(list, data.get("reverse", {}))
            self.file_edges = defaultdict(list, data.get("file_edges", {}))
            self.file_reverse = defaultdict(
                list,
                data.get("file_reverse", {})
            )
            self._built = True

            print(
                f"[DependencyGraph] Loaded from cache: "
                f"{len(self.edges)} symbols."
            )

            return True

        except Exception as e:
            print(f"[DependencyGraph] Load error: {e}")
            return False

    def _dedupe(
        self,
        graph: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:

        return {
            key: list(dict.fromkeys(values))
            for key, values in graph.items()
        }

    def _bfs(
        self,
        graph: Dict[str, List[str]],
        start: str,
        depth: int
    ) -> List[str]:

        visited: Set[str] = set()
        frontier = {start}

        for _ in range(depth):
            next_frontier: Set[str] = set()

            for node in frontier:
                for neighbor in graph.get(node, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)

            frontier = next_frontier

        visited.discard(start)

        return list(visited)
