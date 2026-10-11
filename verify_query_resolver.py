# verify_query_resolver.py
import sys
import os
from pathlib import Path

# Add .agent to path
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from retrieval.query_resolver import QueryResolver
from repository_intelligence.db.connection import SessionLocal
from retrieval.retriever import CodeRetriever

def run_tests():
    print("\n" + "=" * 60)
    print("  Query Resolver & Directed Retrieval Verification")
    print("=" * 60)

    db_session = SessionLocal()
    try:
        # Test 1: QueryResolver Extraction
        print("[Test 1] Testing QueryResolver extraction parameters...")
        resolver = QueryResolver()
        resolved = resolver.resolve("Add logging to Employee Service")
        
        print(f"  Query: 'Add logging to Employee Service'")
        print(f"  Mode: {resolved.mode}")
        print(f"  Symbol Names: {resolved.symbol_names}")
        print(f"  Graph Op: {resolved.graph_op}")
        
        assert "EmployeeService" in resolved.symbol_names, f"Expected EmployeeService in symbol_names, got {resolved.symbol_names}"
        print("  [OK] QueryResolver extraction verified successfully.")

        # Test 2: CodeRetriever Directed Retrieval Integration
        print("\n[Test 2] Testing CodeRetriever Directed Retrieval fallback...")
        # Stub the retriever config
        from retrieval.embedding_engine import EmbeddingEngine
        from retrieval.vector_store import VectorStore
        
        engine = EmbeddingEngine()
        retriever = CodeRetriever(
            repo_root="."
        )
        # Mock chunks representing index to avoid full HNSW loading latency if cache absent
        retriever.chunks = [
            {"file": "backend/src/main/java/com/example/service/EmployeeService.java", "symbol": "EmployeeService"},
            {"file": "backend/src/main/java/com/example/service/impl/EmployeeServiceImpl.java", "symbol": "EmployeeServiceImpl"},
            {"file": "backend/src/main/java/com/example/spec/EmployeeSpecifications.java", "symbol": "alwaysTrue"}
        ]
        
        # Run search
        results = retriever.search("Add logging to Employee Service", top_k=5)
        print(f"  Search returned {len(results)} chunks.")
        for r in results:
            print(f"    - Chunk: {r.get('chunk', {}).get('file')} (Score: {r.get('score')})")
            
        assert len(results) > 0, "Should resolve at least one chunk"
        print("  [OK] CodeRetriever directed retrieval integration verified.")

    finally:
        db_session.close()

    print("\n" + "=" * 60)
    print("  ALL QUERY RESOLVER & DIRECTED RETRIEVAL TESTS PASSED! [OK]")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_tests()
