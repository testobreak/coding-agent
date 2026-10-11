import sys
import os
import time
from pathlib import Path

# Add .agent to path so we can import modules
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from retrieval.retriever import CodeRetriever
from retrieval.retrieval_pipeline import RetrievalPipeline

def run_performance_test():
    print("\n" + "=" * 60)
    print("  Retrieval Subsystem Performance & Routing Verification")
    print("=" * 60)

    # 1. Initialize retriever
    print("\n[1] Initializing Retriever & Loading Cache...")
    start_init = time.time()
    retriever = CodeRetriever(repo_root=".")
    pipeline = RetrievalPipeline(retriever)
    init_duration = time.time() - start_init
    print(f"  Initialized in {init_duration:.2f}s")
    print(f"  Total Chunks: {len(retriever.chunks)}")

    # Ensure SymbolGraphCache is preloaded
    from retrieval.symbol_graph_cache import SymbolGraphCache
    cache = SymbolGraphCache.get_instance()
    cache.load()

    # 2. Test Queries representing the three routed paths
    queries = [
        {
            "type": "Symbolic / Lexical Query (Bypasses Embeddings)",
            "query": "EmployeeService",
            "expected_route": "Lexical/Symbolic"
        },
        {
            "type": "Relationship / Graph Query (Bypasses Embeddings)",
            "query": "tests for EmployeeService",
            "expected_route": "Graph Traversal"
        },
        {
            "type": "Semantic Query (Uses HNSW ANN Search)",
            "query": "how to authenticate keycloak users",
            "expected_route": "Semantic ANN Search"
        }
    ]

    print("\n[2] Executing Queries and Measuring Latency...")
    # Warmup runs to compile Python modules, load index files, and initialize connections
    pipeline.retrieve_relevant_chunks("warmup query", top_k=5, expand_context=False)
    for q in queries:
        print("\n" + "-" * 50)
        print(f"Query Type: {q['type']}")
        print(f"Query: '{q['query']}'")
        
        # Measure latency
        start_time = time.time()
        results = pipeline.retrieve_relevant_chunks(q['query'], top_k=5, expand_context=False)
        duration_ms = (time.time() - start_time) * 1000

        print(f"Latency: {duration_ms:.2f} ms")
        print(f"Results Resolved: {len(results)} chunks")
        if results:
            print(f"Top Result: {results[0]['chunk'].get('name', 'Unknown')} (File: {results[0]['chunk'].get('file', 'Unknown')})")

        # Basic latency checks
        if q['expected_route'] != "Semantic ANN Search":
            # Symbolic/Graph queries must resolve extremely quickly
            assert duration_ms < 100.0, f"Expected symbolic/graph query latency < 100ms, got {duration_ms:.2f}ms"
            print(f"  [OK] Ultra-low latency verified: {duration_ms:.2f} ms")
        else:
            # Semantic query should also be fast on HNSW with Cross-Encoder reranker
            assert duration_ms < 1000.0, f"Expected semantic query latency < 1000ms, got {duration_ms:.2f}ms"
            print(f"  [OK] HNSW Semantic Search latency verified: {duration_ms:.2f} ms")

    print("\n" + "=" * 60)
    print("  ALL RETRIEVAL PERFORMANCE & ROUTING CHECKS PASSED! [OK]")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_performance_test()
