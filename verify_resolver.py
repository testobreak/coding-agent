import sys
from pathlib import Path

# Add .agent to path so we can import modules if needed
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.file import File
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.services.symbol_resolver import SymbolResolver


def run_tests():
    print("\n" + "=" * 60)
    print("  SymbolResolver Integration Tests")
    print("=" * 60)

    from repository_intelligence.db.connection import Base, engine
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    resolver = SymbolResolver()

    try:
        # 1. Setup mock repo, files, and symbols in a transaction
        print("\n[1] Creating mock repository, files, and symbols...")
        
        repo = Repository(
            name="TestMockRepo",
            root_path="/mock/repo/path"
        )
        session.add(repo)
        session.flush()

        file_a = File(
            repository_id=repo.id,
            path="backend/src/main/java/com/hrms/employee/EmployeeController.java",
            language="java",
            file_hash="hash_a",
            size_bytes=1000
        )
        file_b = File(
            repository_id=repo.id,
            path="backend/src/main/java/com/hrms/employee/EmployeeService.java",
            language="java",
            file_hash="hash_b",
            size_bytes=1500
        )
        session.add(file_a)
        session.add(file_b)
        session.flush()

        sym_controller = Symbol(
            repository_id=repo.id,
            file_id=file_a.id,
            name="EmployeeController",
            qualified_name="com.hrms.employee.EmployeeController",
            symbol_type="CLASS",
            start_line=10,
            end_line=50,
            signature="public class EmployeeController",
            source_hash="sha_controller"
        )
        sym_service = Symbol(
            repository_id=repo.id,
            file_id=file_b.id,
            name="EmployeeService",
            qualified_name="com.hrms.employee.EmployeeService",
            symbol_type="CLASS",
            start_line=5,
            end_line=40,
            signature="public class EmployeeService",
            source_hash="sha_service"
        )
        sym_impl = Symbol(
            repository_id=repo.id,
            file_id=file_b.id,
            name="EmployeeServiceImpl",
            qualified_name="com.hrms.employee.EmployeeServiceImpl",
            symbol_type="CLASS",
            start_line=15,
            end_line=60,
            signature="public class EmployeeServiceImpl",
            source_hash="sha_impl"
        )
        session.add(sym_controller)
        session.add(sym_service)
        session.add(sym_impl)
        session.flush()

        # Add import relationship: EmployeeController USES com.hrms.employee.EmployeeService
        rel_import = SymbolRelationship(
            repository_id=repo.id,
            source_file_id=file_a.id,
            source_symbol_id=sym_controller.id,
            target_name="com.hrms.employee.EmployeeService",
            relationship_type="USES",
            confidence=1.0
        )
        session.add(rel_import)
        session.flush()

        print("  [OK] Setup complete.")

        # -------------------------------------------------------------
        # Test 1: Fully Qualified Name Match
        # -------------------------------------------------------------
        print("\n[Test 1] Testing Strategy 1: Fully Qualified Name Match...")
        resolved = resolver.resolve(
            session=session,
            repository_id=repo.id,
            target_name="com.hrms.employee.EmployeeService"
        )
        assert isinstance(resolved, list), "Expected list of candidates"
        assert len(resolved) > 0, "Expected at least one candidate"
        assert resolved[0].id == sym_service.id, f"Resolved to incorrect ID: {resolved[0].id}"
        print("  [OK] Success: Resolved fully qualified name directly.")

        # -------------------------------------------------------------
        # Test 2: Import-Context Match
        # -------------------------------------------------------------
        print("\n[Test 2] Testing Strategy 2: Context-Aware Import Matching...")
        resolved = resolver.resolve(
            session=session,
            repository_id=repo.id,
            target_name="EmployeeService",
            source_file=file_a
        )
        assert isinstance(resolved, list), "Expected list of candidates"
        assert len(resolved) > 0, "Expected at least one candidate"
        assert resolved[0].id == sym_service.id, "Resolved to incorrect ID"
        print("  [OK] Success: Resolved simple name using import 'USES' relationship context.")

        # -------------------------------------------------------------
        # Test 3: Same-Package Match
        # -------------------------------------------------------------
        print("\n[Test 3] Testing Strategy 3: Same-Package Matching (no explicit import)...")
        # Remove import relationship to test same-package package inference
        session.delete(rel_import)
        session.flush()

        resolved = resolver.resolve(
            session=session,
            repository_id=repo.id,
            target_name="EmployeeService",
            source_file=file_a
        )
        assert isinstance(resolved, list), "Expected list of candidates"
        assert len(resolved) > 0, "Expected at least one candidate"
        assert resolved[0].id == sym_service.id, "Resolved to incorrect ID"
        print("  [OK] Success: Resolved simple name based on source file's package path namespace.")

        # -------------------------------------------------------------
        # Test 4: Fuzzy Fallback Suffix Match
        # -------------------------------------------------------------
        print("\n[Test 4] Testing Strategy 4: Fuzzy Suffix Fallback Match (no file context)...")
        resolved = resolver.resolve(
            session=session,
            repository_id=repo.id,
            target_name="EmployeeService"
        )
        assert isinstance(resolved, list), "Expected list of candidates"
        assert len(resolved) > 0, "Expected at least one candidate"
        assert resolved[0].id == sym_service.id, "Resolved to incorrect ID"
        print("  [OK] Success: Resolved simple name with fallback fuzzy suffix matching.")

        # -------------------------------------------------------------
        # Test 5: Multi-Stage Heuristic Re-ranking
        # -------------------------------------------------------------
        print("\n[Test 5] Testing Strategy 5: Multi-Stage Heuristic Re-ranking...")
        # When querying for "EmployeeService", we have multiple candidates:
        # Candidate 1: com.hrms.employee.EmployeeService (Exact match: +200, namespace/package: +50, proximity: +30)
        # Candidate 2: com.hrms.employee.EmployeeServiceImpl (Prefix match: +40, namespace/package: +50, proximity: +30)
        # Therefore, Candidate 1 should score higher than Candidate 2.
        
        resolved = resolver.resolve(
            session=session,
            repository_id=repo.id,
            target_name="EmployeeService",
            source_file=file_a
        )
        assert isinstance(resolved, list), "Expected resolver to return list"
        assert len(resolved) >= 2, f"Expected at least 2 candidates, got {len(resolved)}"
        
        print("  Ranked Candidates in Results:")
        for idx, cand in enumerate(resolved):
            print(f"    - Rank {idx+1}: {cand.qualified_name} (Name: {cand.name})")

        assert resolved[0].id == sym_service.id, f"Expected highest rank to be EmployeeService, got {resolved[0].name}"
        assert resolved[1].id == sym_impl.id, f"Expected second rank to be EmployeeServiceImpl, got {resolved[1].name}"
        print("  [OK] Success: Heuristic Multi-Stage Ranker accurately prioritized exact match over prefix match.")

        print("\n" + "=" * 60)
        print("  ALL TESTS PASSED SUCCESSFULLY! [OK]")
        print("=" * 60 + "\n")

    except AssertionError as ae:
        print(f"\n[FAIL] ASSERTION ERROR: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Crucial: Roll back the transaction so we do not leave any mock garbage in the DB!
        print("[Cleanup] Rolling back transaction to keep database clean...")
        session.rollback()
        session.close()


if __name__ == "__main__":
    run_tests()
