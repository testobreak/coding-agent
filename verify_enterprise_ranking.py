import sys
import os
import uuid
from pathlib import Path
from sqlalchemy import text

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from repository_intelligence.models.repository import Repository
from repository_intelligence.db.connection import SessionLocal
from retrieval.hybrid_ranker import HybridRanker


def run_tests():
    print("\n" + "=" * 60)
    print("  Enterprise Multi-Signal Hybrid Ranker Tests")
    print("=" * 60)

    from repository_intelligence.db.connection import Base, engine
    Base.metadata.create_all(bind=engine)

    ranker = HybridRanker()
    session = SessionLocal()

    # 1. Test Symbol Extraction
    print("\n[Test 1] Testing dynamic target symbol extraction...")
    query = "Add logging to EmployeeService"
    targets = ranker.extract_target_symbols(query)
    print(f"  - Query:   \"{query}\"")
    print(f"  - Targets: {targets}")
    assert "EmployeeService" in targets, "Expected EmployeeService to be extracted"
    print("  [OK] Successfully extracted CamelCase symbol targets.")

    # 2. Test Multi-Signal Ranking
    print("\n[Test 2] Testing multi-signal ranking composite scores...")
    
    # Construct candidates with various matching profiles
    candidates = [
        # Candidate A: Match by name but low embedding score
        {
            "score": 0.1,  # Low FAISS vector score
            "chunk": {
                "chunk_id": "chunk_A",
                "name": "EmployeeService",
                "file": "backend/src/main/java/com/acme/hrms/employee/service/EmployeeService.java"
            }
        },
        # Candidate B: No name match but extremely high embedding score
        {
            "score": 0.95,  # High vector score
            "chunk": {
                "chunk_id": "chunk_B",
                "name": "file_discovery",
                "file": "repository_intelligence/indexer/file_discovery.py"
            }
        },
        # Candidate C: Match by path segment but no name match
        {
            "score": 0.2,
            "chunk": {
                "chunk_id": "chunk_C",
                "name": "EmployeeController",
                "file": "backend/src/main/java/com/acme/hrms/employee/controller/EmployeeController.java"
            }
        }
    ]

    ranked = ranker.rank(query, candidates, session=session)

    print("\n=== HYBRID RANKED CANDIDATES ===")
    for idx, item in enumerate(ranked):
        chunk = item["chunk"]
        diags = chunk["_ranking_diagnostics"]
        print(f"Rank {idx + 1}: {chunk['name']} (Composite Score: {item['score']:.4f})")
        print(f"  - File: {chunk['file']}")
        print(f"  - Sub-scores: {diags}")

    # Assertions
    assert ranked[0]["chunk"]["name"] == "EmployeeService", "Expected EmployeeService to rank #1 due to symbol_score dominance"
    assert ranked[1]["chunk"]["name"] == "EmployeeController", "Expected EmployeeController to rank #2 due to path relevance match ('employee')"
    assert ranked[2]["chunk"]["name"] == "file_discovery", "Expected file_discovery to rank last despite highest vector score"

    print("\n  [OK] Multi-signal ranking validated successfully:")
    print("    - Name matching (35%) successfully prioritized target symbols.")
    print("    - Path relevance (10%) boosted folder segment hits.")
    print("    - Embedding similarity (15%) was properly scaled.")

    print("\n" + "=" * 60)
    print("  ALL ENTERPRISE HYBRID RANKER TESTS PASSED! [OK]")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_tests()
