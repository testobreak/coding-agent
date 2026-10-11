# verify_target_resolver.py
import sys
import os
from pathlib import Path

# Add .agent to path
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from context.target_resolver import TargetResolver
from repository_intelligence.db.connection import SessionLocal

def run_tests():
    print("\n" + "=" * 60)
    print("  Target Resolver Verification")
    print("=" * 60)

    from repository_intelligence.models.repository import Repository
    from repository_intelligence.models.file import File
    from repository_intelligence.models.symbol import Symbol

    db_session = SessionLocal()
    repo = None
    file_row = None
    symbol_row = None
    try:
        # Create mock data
        repo = Repository(name="CodingAgent-TargetResolver-Test", root_path=os.getcwd())
        db_session.add(repo)
        db_session.flush()

        file_row = File(
            repository_id=repo.id,
            path="backend/src/main/java/com/acme/app/me/MeController.java",
            language="java",
            file_hash="mock_hash_target_resolver",
            size_bytes=1000
        )
        db_session.add(file_row)
        db_session.flush()

        symbol_row = Symbol(
            repository_id=repo.id,
            file_id=file_row.id,
            name="MeController",
            qualified_name="com.acme.app.me.MeController",
            symbol_type="class",
            start_line=1,
            end_line=20,
            source_hash="mock_source_hash_target_resolver"
        )
        db_session.add(symbol_row)
        db_session.flush()
        db_session.commit()

        resolver = TargetResolver(db_session)
        resolution = resolver.resolve("Add logging to MeController")
        
        print(f"  Resolved Target Handles: {resolution}")
        assert len(resolution) > 0, "Should resolve at least one symbol handle."
        handle = resolution[0]
        assert handle.fqn.endswith("MeController"), f"Expected MeController in FQN, got '{handle.fqn}'"
        assert handle.file_path == file_row.path, f"Expected '{file_row.path}', got '{handle.file_path}'"
        print("  [OK] TargetResolver successfully extracted deterministic targets.")
    finally:
        if repo or file_row or symbol_row:
            try:
                if symbol_row: db_session.delete(symbol_row)
                if file_row: db_session.delete(file_row)
                if repo: db_session.delete(repo)
                db_session.commit()
            except Exception as e:
                print(f"Cleanup warning: {e}")
        db_session.close()

    print("\n" + "=" * 60)
    print("  ALL TARGET RESOLVER TESTS PASSED! [OK]")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_tests()
