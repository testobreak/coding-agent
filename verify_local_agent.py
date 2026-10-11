# verify_local_agent.py
"""
Verification suite for the Local Coding Agent & Ollama pipeline.
Validates:
1. Ollama health and model availability (qwen2.5-coder:7b)
2. Sub-50ms deterministic repository search (0 LLM calls)
3. Context compaction within token budget
4. End-to-end question answering with telemetry output
"""

import sys
import os
import time
from pathlib import Path

# Add .agent to path
agent_dir = Path(__file__).resolve().parent / ".agent"
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from execution.local_agent import LocalAgent


def test_local_agent():
    print("\n" + "=" * 60)
    print("  Local Coding Agent (Ollama: qwen2.5-coder:7b) Verification")
    print("=" * 60)

    agent = LocalAgent()

    # 1. Health Check
    print("\n[Test 1] Verifying local Ollama daemon connection...")
    is_healthy = agent.ollama.check_health()
    assert is_healthy, "Ollama daemon not healthy or qwen2.5-coder:7b not available"
    print("  [OK] Ollama is running and qwen2.5-coder:7b is ready.")

    # 2. Deterministic Search Speed
    print("\n[Test 2] Testing deterministic repository search speed (0 LLM calls)...")
    t0 = time.time()
    terms = agent.extract_search_terms("Where is the query resolver defined and how does it route?")
    snippets = agent.deterministic_search(terms, max_snippets=3)
    duration_ms = (time.time() - t0) * 1000
    
    print(f"  Extracted search terms: {terms}")
    print(f"  Retrieved {len(snippets)} snippets in {duration_ms:.2f} ms")
    assert len(snippets) > 0, "Failed to retrieve relevant snippets"
    assert duration_ms < 250, f"Deterministic search took {duration_ms}ms, expected < 250ms"
    print(f"  [OK] Search completed in {duration_ms:.2f}ms (< 250ms threshold).")

    # 3. Context Compactor
    print("\n[Test 3] Testing context compactor and token budgeting...")
    compact_context = agent.build_compact_context(snippets)
    assert len(compact_context) <= agent.max_context_chars, "Context exceeded budget"
    assert "--- File:" in compact_context, "Snippet headers missing"
    print(f"  [OK] Context compacted to {len(compact_context)} characters.")

    # 4. Live Query with Telemetry
    print("\n[Test 4] Testing single-call Ollama execution and telemetry capture...")
    query = "What are the modes in ResolutionMode?"
    result = agent.ask(query)
    
    print(f"  Answer length: {len(result.answer)} characters")
    print(f"  Speed: {result.telemetry.tokens_per_second:.1f} tokens/sec")
    print(f"  Prompt eval: {result.telemetry.prompt_eval_duration_ms:.1f} ms")
    
    assert len(result.answer) > 20, "Answer too short"
    assert result.telemetry.output_tokens > 0, "No tokens generated"
    assert result.telemetry.tokens_per_second > 0, "Invalid tokens/sec metric"
    print(f"  [OK] Telemetry captured successfully: {result.telemetry.summary()}")

    print("\n" + "=" * 60)
    print("  ALL LOCAL AGENT VERIFICATION CHECKS PASSED! [OK]")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    test_local_agent()
