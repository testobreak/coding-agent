# context/test_discovery.py
#
# Test Discovery logic. Automatically gathers test symbol references.

from typing import List, Dict, Any
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Symbol
from repository_intelligence.models.symbol import Test as DBTest
from repository_intelligence.models.file import File
from context.context_package import ResolvedSymbol
from sqlalchemy import or_

class TestDiscovery:
    def discover(self, target_symbols: List[ResolvedSymbol], session=None) -> List[Dict[str, Any]]:
        discovered_tests = []
        close_session = False
        if session is None:
            session = SessionLocal()
            close_session = True
            
        try:
            # 1. Look up by relationship database tests
            names = [s.name for s in target_symbols]
            db_symbols = session.query(Symbol.id).filter(
                or_(
                    Symbol.name.in_(names),
                    Symbol.qualified_name.in_(names)
                )
            ).all()
            symbol_ids = [s[0] for s in db_symbols]
            
            if symbol_ids:
                tests = session.query(DBTest).join(File, DBTest.file_id == File.id).filter(
                    DBTest.target_symbol_id.in_(symbol_ids)
                ).all()
                for test in tests:
                    discovered_tests.append({
                        "name": test.name,
                        "file_path": test.file.path if test.file else "",
                        "type": "unit_test"
                    })
            
            # 2. Heuristic suffix match (e.g. EmployeeService -> EmployeeServiceTest)
            for sym in target_symbols:
                heuristic_names = [f"{sym.name}Test", f"{sym.name}Tests", f"{sym.name}Spec"]
                heuristic_symbols = session.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                    Symbol.name.in_(heuristic_names)
                ).all()
                for hsym in heuristic_symbols:
                    discovered_tests.append({
                        "name": hsym.name,
                        "file_path": hsym.file.path if hsym.file else "",
                        "type": "heuristic_test"
                    })
        except Exception as e:
            print(f"[TestDiscovery] Warning: Failed test discovery: {e}")
        finally:
            if close_session:
                session.close()
            
        # Deduplicate
        seen = set()
        deduped = []
        for t in discovered_tests:
            key = (t["name"], t["file_path"])
            if key not in seen:
                seen.add(key)
                deduped.append(t)
                
        return deduped
