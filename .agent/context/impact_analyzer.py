# context/impact_analyzer.py
#
# Symbol-centric ImpactAnalyzer. Computes affected symbols (blast radius)
# and affected tests to evaluate risk.

from dataclasses import dataclass, field
from typing import List, Set, Dict, Any, Optional
from sqlalchemy import or_
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.symbol import Test as DBTest
from repository_intelligence.models.file import File
from editing.symbol_handle import SymbolHandle

@dataclass
class ImpactReport:
    affected_symbols: List[SymbolHandle] = field(default_factory=list)
    affected_tests: List[SymbolHandle] = field(default_factory=list)
    risk_score: float = 0.0
    implementations: List[SymbolHandle] = field(default_factory=list)
    interfaces: List[SymbolHandle] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"ImpactReport("
            f"affected_symbols={len(self.affected_symbols)}, "
            f"affected_tests={len(self.affected_tests)}, "
            f"implementations={len(self.implementations)}, "
            f"interfaces={len(self.interfaces)}, "
            f"risk_score={self.risk_score:.2f}"
            f")"
        )

class ImpactAnalyzer:
    def __init__(self, db_session=None):
        self.db_session = db_session

    def analyze(self, target_symbol: SymbolHandle, session=None) -> ImpactReport:
        """
        Analyzes the blast radius and risk score for a target symbol.
        """
        if not target_symbol or target_symbol.symbol_id.startswith("sym_fallback"):
            return ImpactReport(risk_score=0.10)

        db_sess = session or self.db_session
        close_session = False
        if db_sess is None:
            db_sess = SessionLocal()
            close_session = True

        affected_symbols = []
        affected_tests = []
        try:
            import uuid
            target_uuid = None
            try:
                target_uuid = uuid.UUID(target_symbol.symbol_id)
            except Exception:
                target_uuid = target_symbol.symbol_id

            # 1. Transitive caller expansion (Upstream callers)
            visited_ids = {target_uuid}
            queue = [target_uuid]
            depth_map = {target_uuid: 0}
            max_depth = 3

            while queue:
                current_id = queue.pop(0)
                current_depth = depth_map[current_id]
                if current_depth >= max_depth:
                    continue

                # Find all symbol relationships where current_id is the target
                # (i.e. source calls target)
                relationships = db_sess.query(SymbolRelationship).filter(
                    SymbolRelationship.target_symbol_id == current_id
                ).all()

                for rel in relationships:
                    if rel.source_symbol_id and rel.source_symbol_id not in visited_ids:
                        source_id = rel.source_symbol_id
                        visited_ids.add(source_id)
                        depth_map[source_id] = current_depth + 1
                        queue.append(source_id)

            # Retrieve symbol handles for all upstream callers
            caller_ids = list(visited_ids - {target_uuid})
            if caller_ids:
                db_symbols = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                    Symbol.id.in_(caller_ids)
                ).all()
                for sym in db_symbols:
                    affected_symbols.append(SymbolHandle(
                        symbol_id=str(sym.id),
                        fqn=sym.qualified_name,
                        kind=sym.symbol_type or "unknown",
                        file_path=sym.file.path if sym.file else "",
                        start_line=sym.start_line if sym.start_line is not None else 1,
                        end_line=sym.end_line if sym.end_line is not None else 1
                    ))

            # 2. Gather affected tests
            all_symbol_ids = [target_uuid] + caller_ids
            # Query tests from database joining File
            db_tests = db_sess.query(DBTest, File.path).join(File, DBTest.file_id == File.id).filter(
                DBTest.target_symbol_id.in_(all_symbol_ids)
            ).all()

            seen_test_keys = set()
            for t, file_path in db_tests:
                key = (t.name, file_path)
                if key not in seen_test_keys:
                    seen_test_keys.add(key)
                    # Resolve to a SymbolHandle or construct one
                    test_symbol = db_sess.query(Symbol).filter(
                        Symbol.name == t.name,
                        Symbol.file_id == t.file_id
                    ).first()
                    
                    if test_symbol:
                        affected_tests.append(SymbolHandle(
                            symbol_id=str(test_symbol.id),
                            fqn=test_symbol.qualified_name,
                            kind="method" if test_symbol.symbol_type == "METHOD" else "class",
                            file_path=file_path,
                            start_line=test_symbol.start_line,
                            end_line=test_symbol.end_line
                        ))
                    else:
                        affected_tests.append(SymbolHandle(
                            symbol_id=str(t.id),
                            fqn=t.name,
                            kind="class",
                            file_path=file_path,
                            start_line=1,
                            end_line=100
                        ))

            # Query heuristic tests for target and callers
            all_names = [target_symbol.fqn.split(".")[-1]] + [s.fqn.split(".")[-1] for s in affected_symbols]
            for name in all_names:
                heuristic_names = [f"{name}Test", f"{name}Tests", f"{name}Spec"]
                db_heuristic_symbols = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                    Symbol.name.in_(heuristic_names)
                ).all()
                for hsym in db_heuristic_symbols:
                    key = (hsym.name, hsym.file.path if hsym.file else "")
                    if key not in seen_test_keys:
                        seen_test_keys.add(key)
                        affected_tests.append(SymbolHandle(
                            symbol_id=str(hsym.id),
                            fqn=hsym.qualified_name,
                            kind=hsym.symbol_type or "class",
                            file_path=hsym.file.path if hsym.file else "",
                            start_line=hsym.start_line if hsym.start_line is not None else 1,
                            end_line=hsym.end_line if hsym.end_line is not None else 1
                        ))

            # 2.5 Query implementations & interfaces
            implementations = []
            impl_relations = db_sess.query(SymbolRelationship).filter(
                SymbolRelationship.target_symbol_id == target_uuid,
                SymbolRelationship.relationship_type.in_(["IMPLEMENTS", "INHERITS", "EXTENDS"])
            ).all()
            for rel in impl_relations:
                if rel.source_symbol_id:
                    sym = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        Symbol.id == rel.source_symbol_id
                    ).first()
                    if sym:
                        implementations.append(SymbolHandle(
                            symbol_id=str(sym.id),
                            fqn=sym.qualified_name,
                            kind=sym.symbol_type or "unknown",
                            file_path=sym.file.path if sym.file else "",
                            start_line=sym.start_line if sym.start_line is not None else 1,
                            end_line=sym.end_line if sym.end_line is not None else 1
                        ))

            interfaces = []
            iface_relations = db_sess.query(SymbolRelationship).filter(
                SymbolRelationship.source_symbol_id == target_uuid,
                SymbolRelationship.relationship_type.in_(["IMPLEMENTS", "INHERITS", "EXTENDS"])
            ).all()
            for rel in iface_relations:
                if rel.target_symbol_id:
                    sym = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        Symbol.id == rel.target_symbol_id
                    ).first()
                    if sym:
                        interfaces.append(SymbolHandle(
                            symbol_id=str(sym.id),
                            fqn=sym.qualified_name,
                            kind=sym.symbol_type or "unknown",
                            file_path=sym.file.path if sym.file else "",
                            start_line=sym.start_line if sym.start_line is not None else 1,
                            end_line=sym.end_line if sym.end_line is not None else 1
                        ))

            # 3. Calculate Risk Score
            # Base risk: 0.10
            # Scale based on size of blast radius
            num_affected = len(affected_symbols)
            num_tests = len(affected_tests)

            risk_score = 0.10
            risk_score += min(0.40, num_affected * 0.05)

            # Test coverage weight: no tests = risk penalty, tests = slight increase in change surface but verified
            if num_tests == 0:
                risk_score += 0.30
            else:
                risk_score += min(0.20, num_tests * 0.03)

            risk_score = max(0.05, min(0.95, risk_score))

        except Exception as e:
            print(f"[ImpactAnalyzer] Warning: Impact analysis failed: {e}")
            risk_score = 0.50
            implementations = []
            interfaces = []
        finally:
            if close_session:
                db_sess.close()

        return ImpactReport(
            affected_symbols=affected_symbols,
            affected_tests=affected_tests,
            implementations=implementations,
            interfaces=interfaces,
            risk_score=round(risk_score, 2)
        )
