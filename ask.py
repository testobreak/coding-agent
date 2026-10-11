#!/usr/bin/env python3
"""
CLI entry point for the Personal Coding Agent (coding-agent).

Usage:
  # Query the current repository:
  python ask.py "explain how the query resolver works"

  # Query ANY external codebase (100% read-only, 0 changes to target code):
  python ask.py --repo /path/to/your/project "find the login implementation and explain how authentication works"
"""

import sys
import os
import argparse
from pathlib import Path

# Add .agent to path
agent_dir = Path(__file__).resolve().parent / ".agent"
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from execution.local_agent import LocalAgent


def parse_args():
    parser = argparse.ArgumentParser(
        description="Personal Coding Agent — Local AI Code Intelligence powered by Ollama",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="+",
        help="Question or instruction for the coding agent (e.g. 'find authentication implementation')",
    )
    parser.add_argument(
        "-r", "--repo",
        dest="repo_root",
        default=os.getenv("CODING_AGENT_REPO", os.getcwd()),
        help="Path to the target codebase to inspect (default: current directory).\nRuns in 100%% read-only mode without modifying target code.",
    )
    parser.add_argument(
        "-m", "--model",
        dest="model",
        default=os.getenv("CODING_AGENT_MODEL", "qwen2.5-coder:7b"),
        help="Ollama model name (default: qwen2.5-coder:7b)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    query = " ".join(args.query)
    target_repo = Path(args.repo_root).resolve()

    if not target_repo.exists() or not target_repo.is_dir():
        print(f"[ERROR] Target repository path does not exist: {target_repo}")
        sys.exit(1)

    print("═" * 70)
    print("🤖 PERSONAL CODING AGENT (coding-agent)")
    print(f"📁 Target Codebase:  {target_repo} [READ-ONLY]")
    print(f"🧠 Local Model:      {args.model} via Ollama")
    print(f"📌 Query:            {query}")
    print("═" * 70)

    agent = LocalAgent(repo_root=str(target_repo), model=args.model)

    # Verify Ollama is ready
    if not agent.ollama.check_health():
        print(f"[ERROR] Could not connect to Ollama at http://localhost:11434 with model '{args.model}'.")
        print(f"Please ensure Ollama is running: 'ollama serve' and 'ollama pull {args.model}'")
        sys.exit(1)

    print("\n🔍 Step 1: Deterministic repository search (0 LLM calls)...")

    # Stream the answer in real-time
    print("🧠 Step 2: Querying local LLM with compacted context (streaming):\n")
    print("-" * 70)

    def print_stream(chunk: str):
        sys.stdout.write(chunk)
        sys.stdout.flush()

    result = agent.ask(query, stream_callback=print_stream)

    print("\n" + "-" * 70)
    print("\n📊 TELEMETRY DASHBOARD")
    print(f"  • Target Repo:           {target_repo}")
    print(f"  • Retrieval Duration:    {result.retrieval_duration_ms:.2f} ms")
    print(f"  • Snippets Found:        {len(result.snippets)}")
    for s in result.snippets:
        print(f"      - {s.file_path}:{s.start_line}-{s.end_line} (matched: '{s.matched_term}')")
    print(f"  • Input (Prompt) Tokens: {result.telemetry.prompt_tokens} tokens")
    print(f"  • Output Tokens:         {result.telemetry.output_tokens} tokens")
    print(f"  • Prompt Eval Time:      {result.telemetry.prompt_eval_duration_ms:.2f} ms")
    print(f"  • Generation Time:       {result.telemetry.generation_duration_ms:.2f} ms")
    print(f"  • Generation Speed:      {result.telemetry.tokens_per_second:.2f} tokens/sec")
    print(f"  • Total Turnaround:      {result.telemetry.total_duration_ms:.2f} ms")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    main()
