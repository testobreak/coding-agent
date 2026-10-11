# retrieval/symbol_graph_cache.py

from collections import defaultdict
from typing import List, Dict, Any, Optional
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.symbol import Test as DBTest
from repository_intelligence.models.file import File

class SymbolGraphCache:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.symbols_by_id = {}
        self.symbols_by_name = defaultdict(list)
        self.symbols_by_qualified_name = {}
        self.relationships_by_target = defaultdict(list)
        self.relationships_by_source = defaultdict(list)
        self.relationships_by_file = defaultdict(list)
        self.tests_by_symbol = defaultdict(list)
        self.tests_by_file = defaultdict(list)
        self.files_by_path = {}
        self.is_loaded = False
        # ── Snapshot isolation ─────────────────────────────────────────────
        # Stamped with the repo snapshot_id at load() time so callers can
        # detect whether the graph has been loaded against a stale repo state.
        self.snapshot_id: str = ""  # set during load()

    def load(self, force=False, session=None, repo_root: str = "."):
        if self.is_loaded and not force:
            return

        print("[SymbolGraphCache] Loading entire symbol graph into hot memory...")
        db_sess = session if session is not None else SessionLocal()
        close_session = True if session is None else False
        try:
            # 1. Load all files
            files = db_sess.query(File).all()
            files_by_id = {f.id: f for f in files}
            for f in files:
                self.files_by_path[f.path] = f.id

            # 2. Load all symbols
            symbols = db_sess.query(Symbol).all()
            for sym in symbols:
                sym_file = files_by_id.get(sym.file_id)
                sym_file_path = sym_file.path if sym_file else ""
                
                sym_data = {
                    "id": str(sym.id),
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "symbol_type": sym.symbol_type or "unknown",
                    "file_path": sym_file_path,
                    "start_line": sym.start_line if sym.start_line is not None else 1,
                    "end_line": sym.end_line if sym.end_line is not None else 1,
                    "parent_symbol_id": str(sym.parent_symbol_id) if sym.parent_symbol_id else None,
                    "signature": sym.signature or ""
                }
                self.symbols_by_id[str(sym.id)] = sym_data
                self.symbols_by_name[sym.name.lower()].append(sym_data)
                self.symbols_by_qualified_name[sym.qualified_name.lower()] = sym_data

            # 3. Load all relationships
            relations = db_sess.query(SymbolRelationship).all()
            for rel in relations:
                rel_data = {
                    "source_symbol_id": str(rel.source_symbol_id) if rel.source_symbol_id else None,
                    "target_symbol_id": str(rel.target_symbol_id) if rel.target_symbol_id else None,
                    "source_file_id": rel.source_file_id,
                    "target_name": rel.target_name,
                    "relationship_type": rel.relationship_type
                }
                if rel.target_symbol_id:
                    self.relationships_by_target[str(rel.target_symbol_id)].append(rel_data)
                if rel.source_symbol_id:
                    self.relationships_by_source[str(rel.source_symbol_id)].append(rel_data)
                if rel.source_file_id:
                    self.relationships_by_file[rel.source_file_id].append(rel_data)

            # 4. Load all tests
            tests = db_sess.query(DBTest).all()
            for t in tests:
                t_file = files_by_id.get(t.file_id)
                t_file_path = t_file.path if t_file else ""
                t_data = {
                    "id": str(t.id),
                    "name": t.name,
                    "target_symbol_id": str(t.target_symbol_id) if t.target_symbol_id else None,
                    "file_id": t.file_id,
                    "file_path": t_file_path
                }
                if t.target_symbol_id:
                    self.tests_by_symbol[str(t.target_symbol_id)].append(t_data)
                if t.file_id:
                    self.tests_by_file[t.file_id].append(t_data)

            self.is_loaded = True
            # Stamp the cache with the current repo snapshot so staleness
            # checks in QueryResolver can detect drift without re-querying the DB.
            try:
                from repository.snapshot_manager import SnapshotManager
                snap = SnapshotManager().current_snapshot(repo_root)
                self.snapshot_id = snap.snapshot_id
                print(f"[SymbolGraphCache] Snapshot stamped: {self.snapshot_id}")
            except Exception:
                self.snapshot_id = ""
            print(f"[SymbolGraphCache] Loaded {len(self.symbols_by_id)} symbols and {len(relations)} relationships successfully.")
        except Exception as e:
            print(f"[SymbolGraphCache] Error loading graph cache: {e}")
        finally:
            if close_session:
                db_sess.close()


    def is_stale(self, current_snapshot_id: str) -> bool:
        """
        Returns True if the graph was loaded against a different repo snapshot
        than the one provided. When True, QueryResolver should cascade to
        SEMANTIC retrieval rather than serving stale graph results.
        """
        return self.snapshot_id != current_snapshot_id

    def get_symbol_by_id(self, sym_id: str) -> Optional[Dict[str, Any]]:
        return self.symbols_by_id.get(str(sym_id))

    def get_symbols_by_name(self, name: str) -> List[Dict[str, Any]]:
        return self.symbols_by_name.get(name.lower(), [])

    def get_symbol_by_qualified_name(self, qn: str) -> Optional[Dict[str, Any]]:
        return self.symbols_by_qualified_name.get(qn.lower())

    def get_callers(self, symbol_id: str) -> List[Dict[str, Any]]:
        caller_ids = [rel["source_symbol_id"] for rel in self.relationships_by_target.get(str(symbol_id), []) if rel["source_symbol_id"]]
        return [self.symbols_by_id[cid] for cid in caller_ids if cid in self.symbols_by_id]

    def get_callees(self, symbol_id: str) -> List[Dict[str, Any]]:
        callees = []
        for rel in self.relationships_by_source.get(str(symbol_id), []):
            if rel["target_symbol_id"] and rel["target_symbol_id"] in self.symbols_by_id:
                callees.append(self.symbols_by_id[rel["target_symbol_id"]])
            elif rel["target_name"]:
                callees.extend(self.get_symbols_by_name(rel["target_name"]))
        return callees

    def get_tests_for_symbols(self, symbol_ids: List[str]) -> List[Dict[str, Any]]:
        results = []
        for sid in symbol_ids:
            results.extend(self.tests_by_symbol.get(str(sid), []))
        return results

    def get_heuristic_tests(self, primary_name: str) -> List[Dict[str, Any]]:
        heuristic_names = [f"{primary_name}Test", f"{primary_name}Tests", f"{primary_name}Spec"]
        results = []
        for name in heuristic_names:
            results.extend(self.get_symbols_by_name(name))
        return results

    def get_dependencies(self, symbol_id: str) -> List[Dict[str, Any]]:
        deps = []
        for rel in self.relationships_by_source.get(str(symbol_id), []):
            if rel["relationship_type"] in ("USES", "INHERITS", "IMPLEMENTS") and rel["target_symbol_id"] in self.symbols_by_id:
                deps.append(self.symbols_by_id[rel["target_symbol_id"]])
        return deps

    def get_interfaces(self, symbol_id: str) -> List[Dict[str, Any]]:
        interfaces = []
        for rel in self.relationships_by_source.get(str(symbol_id), []):
            if rel["relationship_type"] in ("IMPLEMENTS", "INHERITS", "EXTENDS") and rel["target_symbol_id"] in self.symbols_by_id:
                interfaces.append(self.symbols_by_id[rel["target_symbol_id"]])
        return interfaces

    def get_implementations(self, symbol_id: str) -> List[Dict[str, Any]]:
        implementations = []
        for rel in self.relationships_by_target.get(str(symbol_id), []):
            if rel["relationship_type"] in ("IMPLEMENTS", "INHERITS", "EXTENDS") and rel["source_symbol_id"] in self.symbols_by_id:
                implementations.append(self.symbols_by_id[rel["source_symbol_id"]])
        return implementations

    def get_related_symbols(self, symbol_id: str) -> List[Dict[str, Any]]:
        related = []
        for rel in self.relationships_by_source.get(str(symbol_id), []):
            if rel["relationship_type"] in ("USES", "DEPENDS") and rel["target_symbol_id"] in self.symbols_by_id:
                related.append(self.symbols_by_id[rel["target_symbol_id"]])
        return related

    def get_imports(self, file_path: str) -> List[str]:
        file_id = self.files_by_path.get(file_path)
        if not file_id:
            return []
        relations = self.relationships_by_file.get(file_id, [])
        return [rel["target_name"] for rel in relations if rel["relationship_type"] == "IMPORTS" and rel["target_name"]]
