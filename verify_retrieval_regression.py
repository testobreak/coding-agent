# verify_retrieval_regression.py
"""
Regression test for surgical implementation evidence retrieval:
Validates that deterministic search captures actual execution statements
rather than just docstrings, class signatures, or imports.
"""

import sys
from pathlib import Path

# Setup agent path
agent_dir = Path(__file__).resolve().parent / ".agent"
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from execution.local_agent import LocalAgent


def test_retrieval_evidence():
    agent = LocalAgent(repo_root=".")
    query = (
        "Where is the Ollama model called, "
        "and how is the response streamed?"
    )
    terms = agent.extract_search_terms(query)
    snippets = agent.deterministic_search(terms)
    context = agent.build_compact_context(snippets)

    required_evidence = {
        ".agent/execution/local_agent.py": [
            "self.ollama.generate(",
        ],
        ".agent/inference/ollama_client.py": [
            "/api/generate",
            "stream_callback(text_chunk)",
        ],
        "ask.py": [
            "agent.ask(",
        ],
    }

    print("============================================================")
    print("  RUNNING RETRIEVAL REGRESSION DIAGNOSTIC")
    print(f"  Query: \"{query}\"")
    print(f"  Extracted Terms: {terms}")
    print("============================================================")

    for s in snippets:
        print(f"Retrieved: {s.file_path} (L{s.start_line}-{s.end_line}, score={s.relevance_score:.1f})")

    print("------------------------------------------------------------")

    failed = False
    for file_path, expected_statements in required_evidence.items():
        file_context = "\n".join(
            s.content
            for s in snippets
            if s.file_path == file_path
        )
        if not file_context:
            print(f"❌ MISSING FILE: {file_path} was not in top retrieved snippets!")
            failed = True
            continue

        for statement in expected_statements:
            in_file = statement in file_context
            in_compact = statement in context
            if not in_file:
                print(f"❌ MISSING STATEMENT in {file_path}: '{statement}'")
                failed = True
            elif not in_compact:
                print(f"❌ DROPPED BY COMPACTION in {file_path}: '{statement}'")
                failed = True
            else:
                print(f"✅ FOUND: {file_path} -> '{statement}'")

    print("============================================================")
    if failed:
        print("FAIL: Implementation evidence missing in retrieved snippets.")
        sys.exit(1)
    else:
        print("PASS: All required implementation evidence retrieved.")
        sys.exit(0)


if __name__ == "__main__":
    test_retrieval_evidence()
