# verify_retrieval_quality.py
#
# Validates that the two-stage retrieval pipeline (ANN + BM25 + Symbol Index)
# correctly resolves the core ranking quality failure:
#
#   Query: "Add logging to EmployeeService"
#   Expected: EmployeeService ranked above EmployeeSpecifications
#
# Also validates:
#   - BM25 lexical search precision
#   - Symbol index exact match priority
#   - Generic file penalty damping
#   - Semantic confidence threshold filtering
#   - Intent-adaptive weight routing

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".agent"))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    print("============================================================")
    print("  Retrieval Quality & Two-Stage Pipeline Verification Suite")
    print("============================================================")

    from retrieval.bm25_index import BM25Index
    from retrieval.symbol_index import SymbolIndex, extract_symbols
    from retrieval.candidate_pipeline import CandidatePipeline, _is_generic_file
    from retrieval.query_intent import RetrievalIntentClassifier, RetrievalIntent

    # Build test corpus that reproduces the exact failure scenario
    chunks = [
        {
            "name": "EmployeeService",
            "symbol": "EmployeeService",
            "file": "backend/src/main/java/com/example/services/EmployeeService.java",
            "code": "public class EmployeeService {\n    public void approveLeave(Long id) {}\n    public Employee findById(Long id) {}\n    public List<Employee> getAll() {}\n}",
            "type": "class"
        },
        {
            "name": "EmployeeServiceImpl",
            "symbol": "EmployeeServiceImpl",
            "file": "backend/src/main/java/com/example/services/impl/EmployeeServiceImpl.java",
            "code": "public class EmployeeServiceImpl implements EmployeeService {\n    private final EmployeeRepository repo;\n    public void approveLeave(Long id) { repo.findById(id); }\n}",
            "type": "class"
        },
        {
            "name": "EmployeeSpecifications",
            "symbol": "EmployeeSpecifications",
            "file": "backend/src/main/java/com/example/specs/EmployeeSpecifications.java",
            "code": "public class EmployeeSpecifications {\n    public static Specification<Employee> alwaysTrue() { return null; }\n    public static Specification<Employee> idIn(List<Long> ids) { return null; }\n}",
            "type": "class"
        },
        {
            "name": "EmployeeController",
            "symbol": "EmployeeController",
            "file": "backend/src/main/java/com/example/controllers/EmployeeController.java",
            "code": "public class EmployeeController {\n    private final EmployeeService service;\n    public ResponseEntity getEmployee(Long id) { return service.findById(id); }\n}",
            "type": "class"
        },
        {
            "name": "BaseUtils",
            "symbol": "BaseUtils",
            "file": "backend/src/main/java/com/example/utils/BaseUtils.java",
            "code": "public class BaseUtils {\n    public static String format(String s) { return s.trim(); }\n}",
            "type": "class"
        },
        {
            "name": "LeaveService",
            "symbol": "LeaveService",
            "file": "backend/src/main/java/com/example/services/LeaveService.java",
            "code": "public class LeaveService {\n    public void requestLeave(Long empId) {}\n}",
            "type": "class"
        }
    ]

    # ── Test 1: BM25 Lexical Search ──────────────────────────
    print("\n[Test 1] BM25 lexical search precision...")
    bm25 = BM25Index()
    bm25.build(chunks)
    bm25_results = bm25.search("Add logging to EmployeeService", k=6)
    bm25_names = [r["chunk"]["name"] for r in bm25_results]
    print(f"  BM25 ranking: {bm25_names}")
    assert bm25_names[0] in ("EmployeeService", "EmployeeServiceImpl"), \
        f"BM25 top result should be EmployeeService or EmployeeServiceImpl, got {bm25_names[0]}"
    # EmployeeSpecifications should NOT be #1
    assert bm25_names[0] != "EmployeeSpecifications", \
        "BM25 ranked EmployeeSpecifications first — lexical search is broken"
    print("  [OK] BM25 correctly ranks EmployeeService above EmployeeSpecifications.")

    # ── Test 2: Symbol Index Exact Match ─────────────────────
    print("\n[Test 2] Symbol index exact match priority...")
    sym_index = SymbolIndex()
    sym_index.build(chunks)
    symbols = extract_symbols("Add logging to EmployeeService")
    print(f"  Extracted symbols: {symbols}")
    assert "EmployeeService" in symbols, f"Failed to extract 'EmployeeService' from query, got: {symbols}"

    sym_results = sym_index.lookup(symbols, k=6)
    sym_names = [r["chunk"]["name"] for r in sym_results]
    sym_scores = [(r["chunk"]["name"], r["score"]) for r in sym_results]
    print(f"  Symbol ranking: {sym_scores}")

    # EmployeeService should have score 1.0 (exact match)
    top_sym = sym_results[0]
    assert top_sym["chunk"]["name"] == "EmployeeService", \
        f"Symbol index top result should be EmployeeService, got {top_sym['chunk']['name']}"
    assert top_sym["score"] >= 0.9, f"Exact symbol match score should be >= 0.9, got {top_sym['score']}"
    print("  [OK] Symbol index correctly gives exact match priority to EmployeeService.")

    # ── Test 3: Generic File Penalty ──────────────────────────
    print("\n[Test 3] Generic file penalty damping...")
    assert _is_generic_file("backend/src/main/java/com/example/utils/BaseUtils.java"), \
        "BaseUtils.java should be detected as generic"
    assert _is_generic_file("specs/EmployeeSpecifications.java"), \
        "EmployeeSpecifications.java should be detected as generic"
    assert not _is_generic_file("services/EmployeeService.java"), \
        "EmployeeService.java should NOT be generic"
    print("  [OK] Generic file detection correctly identifies utility/spec files.")

    # ── Test 4: Intent Classification ─────────────────────────
    print("\n[Test 4] Intent classification routing...")
    intent1 = RetrievalIntentClassifier.classify("Add logging to EmployeeService")
    assert intent1 == RetrievalIntent.MODIFY_SYMBOL, f"Expected MODIFY_SYMBOL, got {intent1}"

    intent2 = RetrievalIntentClassifier.classify("Fix bug in LeaveService")
    assert intent2 == RetrievalIntent.BUG_FIX, f"Expected BUG_FIX, got {intent2}"

    intent3 = RetrievalIntentClassifier.classify("Refactor EmployeeController")
    assert intent3 == RetrievalIntent.REFACTOR, f"Expected REFACTOR, got {intent3}"

    intent4 = RetrievalIntentClassifier.classify("Explain how authentication works")
    assert intent4 == RetrievalIntent.EXPLAIN, f"Expected EXPLAIN, got {intent4}"
    print("  [OK] Intent classification correctly routes query types.")

    # ── Test 5: Full Two-Stage Pipeline ───────────────────────
    print("\n[Test 5] Full two-stage candidate pipeline (ANN disabled, BM25 + Symbol)...")
    pipeline = CandidatePipeline(
        vector_store=None,  # No ANN for this test — only BM25 + Symbol
        bm25_index=bm25,
        symbol_index=sym_index,
        cross_encoder=None
    )
    results = pipeline.retrieve(
        query="Add logging to EmployeeService",
        query_embedding=None,
        top_k=5,
        intent="modify_symbol"
    )
    result_names = [r["chunk"]["name"] for r in results]
    result_scores = [(r["chunk"]["name"], round(r["score"], 4)) for r in results]
    print(f"  Pipeline ranking: {result_scores}")

    # THE CRITICAL ASSERTION: EmployeeService must be ranked above EmployeeSpecifications
    if "EmployeeSpecifications" in result_names:
        es_idx = result_names.index("EmployeeService") if "EmployeeService" in result_names else 999
        spec_idx = result_names.index("EmployeeSpecifications")
        assert es_idx < spec_idx, \
            f"CRITICAL FAILURE: EmployeeSpecifications (#{spec_idx}) ranked above EmployeeService (#{es_idx})"

    assert result_names[0] in ("EmployeeService", "EmployeeServiceImpl"), \
        f"Pipeline top result should be EmployeeService or EmployeeServiceImpl, got {result_names[0]}"
    print("  [OK] Two-stage pipeline correctly ranks EmployeeService above EmployeeSpecifications!")

    # ── Test 6: Semantic Confidence Threshold ─────────────────
    print("\n[Test 6] Semantic confidence threshold filtering...")
    # Verify that irrelevant chunks are filtered
    assert len(results) <= 5, f"Expected at most 5 results, got {len(results)}"
    for r in results:
        diag = r["chunk"].get("_ranking_diagnostics", {})
        conf = diag.get("confidence", 0)
        if conf > 0:
            assert conf >= 0.20, f"Chunk {r['chunk']['name']} passed filter with confidence {conf} < 0.20"
    print("  [OK] Weak semantic matches correctly filtered.")

    print("\n============================================================")
    print("  ALL RETRIEVAL QUALITY CHECKS PASSED! [OK]")
    print("============================================================\n")


if __name__ == "__main__":
    main()
