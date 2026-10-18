# verify_evidence_budget.py
"""
Regression test for three-span evidence completeness and retrieval coordination:
1. Validates that ASTEvidenceSelector preserves all three critical evidence spans:
   - OllamaClient.generate signature (L77-85)
   - /api/generate endpoint (L108-114)
   - Streaming callback (L118-141)
   under 3-span, 4-span, and 6-span budgets.
2. Validates RetrievalCoordinator integrating CandidateMerger with AST evidence extraction.
"""

import sys
from pathlib import Path

# Setup agent path
agent_dir = Path(__file__).resolve().parent / ".agent"
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from retrieval.ast_evidence_selector import ASTEvidenceSelector
from retrieval.retrieval_coordinator import RetrievalCoordinator
from execution.local_agent import LocalAgent


def test_three_span_evidence_budget():
    print("============================================================")
    print("  TEST 1: THREE-SPAN EVIDENCE BUDGET REGRESSION")
    print("============================================================")
    
    file_path = ".agent/inference/ollama_client.py"
    source_path = Path(file_path)
    assert source_path.exists(), f"Source file {file_path} not found"
    source = source_path.read_text(encoding="utf-8")

    query = "Where is the Ollama model called, and how is the response streamed?"
    selector = ASTEvidenceSelector()

    expected_spans = {
        "signature": (77, 85),
        "endpoint": (108, 114),
        "callback": (118, 141),
    }

    budgets = [3, 4, 6]
    for budget in budgets:
        spans = selector.select_python(
            file_path=file_path,
            source=source,
            query=query,
            max_spans=budget,
            max_lines=25,
        )
        print(f"\nEvaluating budget: {budget} spans (retrieved {len(spans)})")
        for s in spans:
            print(f"  [{s.evidence_type}] {s.symbol_name}: L{s.start_line}-{s.end_line} (score={s.score:.1f})")

        found_types = {s.evidence_type: (s.start_line, s.end_line) for s in spans}
        for exp_type, (exp_start, exp_end) in expected_spans.items():
            assert exp_type in found_types, (
                f"Missing evidence type '{exp_type}' in budget {budget}!"
            )
            act_start, act_end = found_types[exp_type]
            assert act_start == exp_start and act_end == exp_end, (
                f"Span range mismatch for '{exp_type}' in budget {budget}: "
                f"expected L{exp_start}-{exp_end}, got L{act_start}-{act_end}"
            )
            print(f"  ✅ Preserved: {exp_type} (L{act_start}-{act_end})")

    print("\n[OK] All three pieces of evidence preserved across 3, 4, and 6 spans.")


def test_overlap_deduplication():
    print("\n============================================================")
    print("  TEST 2: OVERLAP DEDUPLICATION")
    print("============================================================")
    file_path = ".agent/inference/ollama_client.py"
    source = Path(file_path).read_text(encoding="utf-8")
    query = "Where is the Ollama model called, and how is the response streamed?"
    selector = ASTEvidenceSelector()

    spans = selector.select_python(
        file_path=file_path,
        source=source,
        query=query,
        max_spans=6,
        max_lines=25,
    )

    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            s1 = spans[i]
            s2 = spans[j]
            overlap = not (s1.end_line < s2.start_line or s2.end_line < s1.start_line)
            assert not overlap, (
                f"Spans overlap: {s1.evidence_type} (L{s1.start_line}-{s1.end_line}) "
                f"and {s2.evidence_type} (L{s2.start_line}-{s2.end_line})"
            )
    print("[OK] All retrieved spans are strictly non-overlapping.")


def test_retrieval_coordinator():
    print("\n============================================================")
    print("  TEST 3: RETRIEVAL COORDINATOR INTEGRATION")
    print("============================================================")
    agent = LocalAgent(repo_root=".")
    coordinator = RetrievalCoordinator(agent)

    query = "Where is the Ollama model called, and how is the response streamed?"
    evidence, result = coordinator.retrieve(query, max_candidates=12, max_parse_files=5)

    print(f"Candidate files ({len(result.candidates)}):")
    for c in result.candidates:
        print(f"  - {c.file_path} (score={c.score:.1f}, mandatory={c.mandatory}, reason={c.reason})")

    print(f"\nExtracted evidence spans ({len(evidence)}):")
    for e in evidence:
        print(f"  - {e.file_path} [{e.evidence_type}] {e.symbol_name} L{e.start_line}-{e.end_line}")

    assert len(result.candidates) > 0, "No file candidates returned"
    assert len(evidence) > 0, "No evidence spans extracted"

    # Verify ollama_client.py evidence is present
    ollama_spans = [e for e in evidence if "ollama_client.py" in e.file_path]
    assert len(ollama_spans) >= 3, "Expected at least 3 spans from ollama_client.py"
    ollama_types = {e.evidence_type for e in ollama_spans}
    assert "signature" in ollama_types, "Missing signature in coordinator output"
    assert "endpoint" in ollama_types, "Missing endpoint in coordinator output"
    assert "callback" in ollama_types, "Missing callback in coordinator output"

    print("\n[OK] RetrievalCoordinator successfully connected Step 1, 2, and 3.")


def test_coordinator_multi_language_and_unsupported_tracking():
    print("\n============================================================")
    print("  TEST 4: MULTI-LANGUAGE & UNSUPPORTED LANGUAGE TRACKING")
    print("============================================================")
    agent = LocalAgent(repo_root=".")
    coordinator = RetrievalCoordinator(agent)

    # 1. Query naming a TypeScript file - should now be extracted!
    query_ts = "Trace extension.ts through agentClient.ts to the Python HTTP server"
    evidence_ts, result_ts = coordinator.retrieve(query_ts)
    retrieved_files = {e.file_path for e in evidence_ts}
    assert any("extension.ts" in f for f in retrieved_files), "extension.ts evidence must be extracted"
    assert any("agentClient.ts" in f for f in retrieved_files), "agentClient.ts evidence must be extracted"
    print("  ✅ TypeScript files successfully parsed by multi_lang_selector.")

    # 2. Check unsupported tracking when a non-supported language file is present in candidates
    from retrieval.candidate_merger import FileCandidate, MergeResult
    mock_result = MergeResult(
        candidates=[FileCandidate(file_path="schema.sql", score=10.0, mandatory=True)],
        missing=[],
        ambiguous=[]
    )
    # Temporary mock retrieve_file_candidates to test unsupported tracking
    orig_fn = agent.retrieve_file_candidates
    agent.retrieve_file_candidates = lambda q, max_candidates=12: mock_result
    try:
        # Create a dummy file if needed
        dummy = Path("schema.sql")
        dummy.write_text("CREATE TABLE test (id INT);", encoding="utf-8")
        coordinator.retrieve("query schema.sql")
        assert "schema.sql" in coordinator.unsupported_files, (
            "schema.sql should be recorded in unsupported_files"
        )
        print("  ✅ Unsupported file type (.sql) tracked in unsupported_files.")
    finally:
        agent.retrieve_file_candidates = orig_fn
        if Path("schema.sql").exists():
            Path("schema.sql").unlink()

    print("[OK] Multi-language extraction and unsupported language tracking verified.")


if __name__ == "__main__":
    test_three_span_evidence_budget()
    test_overlap_deduplication()
    test_retrieval_coordinator()
    test_coordinator_multi_language_and_unsupported_tracking()
    print("\n============================================================")
    print("  ALL EVIDENCE BUDGET & COORDINATOR TESTS PASSED! [100% GREEN]")
    print("============================================================\n")
