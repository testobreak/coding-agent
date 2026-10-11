#!/usr/bin/env python3
"""
CLI entry point for Level 3: Targeted Code Modifications with Validation and Human Approval.

Usage:
  python edit.py "in math.py, add a check for division by zero"
  python edit.py --repo /path/to/any/project --file src/auth.py "add null check for token"
"""

import sys
import os
import argparse
from pathlib import Path

# Add .agent to path
agent_dir = Path(__file__).resolve().parent / ".agent"
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from execution.local_agent import LocalAgent, PatchProposal


def colorize_diff(diff_text: str) -> str:
    """Adds ANSI colors to unified diff output."""
    lines = diff_text.splitlines()
    colored = []
    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            colored.append(f"\033[1;37m{line}\033[0m")
        elif line.startswith("@@"):
            colored.append(f"\033[36m{line}\033[0m")
        elif line.startswith("+"):
            colored.append(f"\033[32m{line}\033[0m")
        elif line.startswith("-"):
            colored.append(f"\033[31m{line}\033[0m")
        else:
            colored.append(line)
    return "\n".join(colored)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Personal Coding Agent — Level 3 Targeted Code Modification",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "instruction",
        nargs="+",
        help="Edit instruction (e.g. 'in UserService.java, add null check for user ID')",
    )
    parser.add_argument(
        "-r", "--repo",
        dest="repo_root",
        default=os.getenv("CODING_AGENT_REPO", os.getcwd()),
        help="Path to the target codebase (default: current directory)",
    )
    parser.add_argument(
        "-f", "--file",
        dest="target_file",
        default=None,
        help="Optional specific file to edit",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Auto-apply patch without interactive prompt",
    )
    parser.add_argument(
        "-m", "--model",
        default=os.getenv("CODING_AGENT_MODEL", "qwen2.5-coder:7b"),
        help="Ollama model name (default: qwen2.5-coder:7b)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    instruction = " ".join(args.instruction)
    target_repo = Path(args.repo_root).resolve()

    if not target_repo.exists() or not target_repo.is_dir():
        print(f"[ERROR] Target repository path does not exist: {target_repo}")
        sys.exit(1)

    print("═" * 70)
    print("🛠️ PERSONAL CODING AGENT — TARGETED PATCH GENERATOR (Level 3)")
    print(f"📁 Target Codebase:  {target_repo}")
    print(f"🧠 Local Model:      {args.model} via Ollama")
    print(f"📌 Instruction:      {instruction}")
    print("═" * 70)

    agent = LocalAgent(repo_root=str(target_repo), model=args.model)

    if not agent.ollama.check_health():
        print(f"[ERROR] Could not connect to Ollama with model '{args.model}'.")
        sys.exit(1)

    print("\n🔍 Step 1: Locating target code & preparing surgical context...")
    
    try:
        proposal: PatchProposal = agent.generate_patch(
            instruction=instruction,
            target_file=args.target_file,
        )
    except Exception as e:
        print(f"\n[ERROR] Patch generation failed: {e}")
        sys.exit(1)

    print(f"\n🎯 Target Resolved: {proposal.file_path} (Lines {proposal.start_line}-{proposal.end_line})")

    # Step 2: Automated Validation
    print("🛡️ Step 2: Automated syntax & balance validation:")
    if proposal.syntax_valid:
        print("  \033[32m✔ Syntax Check: PASSED (No parse or balance errors)\033[0m")
    else:
        print(f"  \033[31m✖ Syntax Check: FAILED ({proposal.syntax_error})\033[0m")
        print("  [WARNING] The generated patch introduces a syntax error. Review carefully.")

    # Step 3: Present Unified Git Diff
    print("\n📄 Step 3: Proposed Unified Diff:")
    print("-" * 70)
    if proposal.diff.strip():
        print(colorize_diff(proposal.diff))
    else:
        print("  [No changes detected between original and patched version]")
        sys.exit(0)
    print("-" * 70)

    # Step 4: Telemetry
    print(f"\n📊 Telemetry: {proposal.telemetry.summary()}")

    # Step 5: Human Approval Gate
    if args.yes:
        print("\n⚡ Auto-applying patch (--yes flag specified)...")
        agent.apply_patch(proposal)
        print(f"✅ \033[32mSuccessfully patched: {proposal.file_path}\033[0m\n")
        return

    print()
    try:
        user_input = input(f"Apply this patch to '{proposal.file_path}'? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n[CANCELLED] Patch rejected.")
        sys.exit(0)

    if user_input in ("y", "yes"):
        agent.apply_patch(proposal)
        print(f"\n✅ \033[32mSuccessfully patched: {proposal.file_path}\033[0m\n")
    else:
        print("\n🚫 [REJECTED] No changes were written to disk.\n")


if __name__ == "__main__":
    main()
