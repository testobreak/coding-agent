import sys
import os
from pathlib import Path
from sqlalchemy import text

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from repository_intelligence.models.repository import Repository
from repository_intelligence.models.file import File
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.symbol import Test as DBTest
from repository_intelligence.db.connection import SessionLocal, Base, engine
from context.context_builder import ContextBuilder


class MockRetrievalPipeline:
    def retrieve_relevant_chunks(self, query, top_k=10, expand_context=True, goal=None):
        return [
            {
                "chunk": {
                    "name": "EmployeeService",
                    "file": "backend/src/main/java/com/hrms/employee/EmployeeService.java"
                }
            }
        ]


def run_tests():
    print("\n" + "=" * 60)
    print("  Enterprise ContextBuilder Integration Tests")
    print("=" * 60)

    # Initialize schema
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    try:
        # 1. Populate mock DB data
        print("\n[1] Creating mock repository, files, symbols, and relationships...")
        
        # Repository
        repo = Repository(name="HRMS", root_path="/Users/ashish/Downloads/HRMS")
        session.add(repo)
        session.flush()

        # File
        file_row = File(
            repository_id=repo.id,
            path="backend/src/main/java/com/hrms/employee/EmployeeService.java",
            language="java",
            file_hash="mock_hash",
            size_bytes=1000
        )
        session.add(file_row)
        session.flush()

        # Symbol
        symbol_row = Symbol(
            repository_id=repo.id,
            file_id=file_row.id,
            name="EmployeeService",
            qualified_name="com.hrms.employee.EmployeeService",
            symbol_type="class",
            start_line=1,
            end_line=20,
            source_hash="mock_source_hash"
        )
        session.add(symbol_row)
        session.flush()

        # Mock File Content on Disk
        # Ensure we write a temporary EmployeeService.java file so SnippetBuilder can read it
        mock_file_path = Path("/Users/ashish/Downloads/HRMS") / file_row.path
        mock_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(mock_file_path, 'w', encoding='utf-8') as f:
            f.write("package com.hrms.employee;\n\npublic class EmployeeService {\n    // Some business logic\n    public void save() {}\n}\n")

        # 2. Instantiate ContextBuilder
        print("\n[2] Instantiating ContextBuilder and running context compilation...")
        pipeline = MockRetrievalPipeline()
        builder = ContextBuilder(pipeline)

        # 3. Compile context passing active test session
        goal = "Add logging to EmployeeService"
        context_pkg = builder.build_planning_context(goal, session=session)

        # 4. Perform validation assertions
        print("\n[3] Running validations on ContextPackage...")
        
        # Validate Goal & Intent
        assert context_pkg.goal == goal, "Goal does not match"
        assert context_pkg.intent.action == "add_feature", f"Unexpected action: {context_pkg.intent.action}"
        assert context_pkg.intent.target == "EmployeeService", f"Unexpected target: {context_pkg.intent.target}"
        assert context_pkg.intent.domain == "service", f"Unexpected domain: {context_pkg.intent.domain}"
        print("  [OK] Intent Analysis validated successfully.")

        # Validate Symbol Resolution
        assert len(context_pkg.target_symbols) == 1, "Expected 1 target symbol resolved"
        resolved = context_pkg.target_symbols[0]
        assert resolved.name == "EmployeeService", f"Unexpected symbol name: {resolved.name}"
        assert resolved.file_path == file_row.path, f"Unexpected file path: {resolved.file_path}"
        print("  [OK] Symbol Resolution validated successfully.")

        # Validate Snippets extraction
        assert len(context_pkg.snippets) == 1, "Expected 1 snippet extracted"
        snippet = context_pkg.snippets[0]
        assert snippet["symbol"] == "EmployeeService", f"Unexpected snippet symbol: {snippet['symbol']}"
        assert "class EmployeeService" in snippet["code"], "Expected class code content in snippet"
        print("  [OK] Snippet boundaries extraction validated successfully.")

        # Validate architectural summary
        assert "Target Symbol(s): EmployeeService" in context_pkg.architectural_summary, "Architectural summary missing target symbol description"
        print("  [OK] Architectural summary compiled successfully.")

        # Cleanup mock file
        if mock_file_path.exists():
            mock_file_path.unlink()

        print("\n" + "=" * 60)
        print("  ALL CONTEXT BUILDER TESTS PASSED SUCCESSFULLY! [OK]")
        print("=" * 60 + "\n")

    except AssertionError as ae:
        print(f"\n[FAIL] ASSERTION FAILURE: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] EXCEPTION ENCOUNTERED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Roll back to keep the DB clean
        session.rollback()
        session.close()


if __name__ == "__main__":
    run_tests()
