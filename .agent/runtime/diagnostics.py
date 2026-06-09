# runtime/diagnostics.py
#
# Prints a clear "what the agent found and what it plans to do"
# BEFORE any patching begins.
#
# Output looks like:
#
#   ╔══════════════════════════════════════════════════════════════╗
#   ║  AGENT DIAGNOSIS                                             ║
#   ╚══════════════════════════════════════════════════════════════╝
#
#   Goal         fix salary deduction null pointer
#   Task type    bug_fix
#
#   Diagnosis
#   ──────────────────────────────────────────────────────────────
#   The calculateSalary() method in EmployeeService.java does not
#   null-check deductions before subtraction. This causes a
#   NullPointerException when deductions is null.
#
#   Files I'll modify
#   ──────────────────────────────────────────────────────────────
#   [1] src/main/java/.../EmployeeService.java
#   [2] src/main/java/.../SalaryController.java
#
#   Code I found
#   ──────────────────────────────────────────────────────────────
#   [1] EmployeeService.java :: calculateSalary()  (MethodDef)
#       return salary - deductions;
#       ...
#

from typing import List, Dict, Any


# ANSI colour helpers (works on Windows 10+ terminal / VS Code terminal)
RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
WHITE  = "\033[97m"


def _hr(char="─", width=66):
    return char * width


def _box(title: str, width=66):
    pad = width - len(title) - 4
    return (
        f"╔{'═' * (width - 2)}╗\n"
        f"║  {BOLD}{title}{RESET}{'  ' + ' ' * pad}║\n"
        f"╚{'═' * (width - 2)}╝"
    )


class DiagnosticsReporter:
    """
    Prints a rich pre-execution diagnosis to the terminal.
    Called by runtime.py right after LLMPlanner.plan() succeeds
    and before the execution loop starts.
    """

    # =========================================================
    # MAIN
    # =========================================================

    def report(
        self,
        goal: str,
        llm_plan: Dict[str, Any],
        retrieved_chunks: List[Dict] = None,
    ) -> None:
        """
        Print the full diagnosis panel.

        Args:
            goal:            The user's original goal string.
            llm_plan:        Dict returned by LLMPlanner.plan().
            retrieved_chunks: Chunks already in state (may be empty at this point).
        """
        retrieved_chunks = retrieved_chunks or []

        print()
        print(CYAN + _box("AGENT DIAGNOSIS") + RESET)
        print()

        # ── Goal + task type ──────────────────────────────────
        task_type = llm_plan.get("task_type", "unknown")
        task_colour = {
            "bug_fix":  RED,
            "feature":  GREEN,
            "refactor": YELLOW,
            "analysis": CYAN,
        }.get(task_type, WHITE)

        print(f"  {DIM}Goal{RESET}       {BOLD}{goal}{RESET}")
        print(f"  {DIM}Task type{RESET}  {task_colour}{BOLD}{task_type.upper()}{RESET}")
        print()

        # ── Reasoning ────────────────────────────────────────
        reasoning = llm_plan.get("reasoning", "")
        if reasoning:
            print(f"  {DIM}Reasoning{RESET}  {reasoning}")
            print()

        # ── Diagnosis ─────────────────────────────────────────
        diagnosis = llm_plan.get("diagnosis", "")
        if diagnosis:
            print(f"  {BOLD}Diagnosis{RESET}")
            print(f"  {_hr()}")
            # Word-wrap at 64 chars
            for line in _wrap(diagnosis, 64):
                print(f"  {line}")
            print()

        # ── Target files ──────────────────────────────────────
        targets = llm_plan.get("target_files", [])
        if targets:
            print(f"  {BOLD}Files I'll modify{RESET}")
            print(f"  {_hr()}")
            for i, path in enumerate(targets[:5], 1):
                print(f"  {DIM}[{i}]{RESET} {YELLOW}{path}{RESET}")
            print()

        # ── Search queries being used ─────────────────────────
        queries = llm_plan.get("suggested_queries", [])
        if queries:
            print(f"  {BOLD}Searching for{RESET}")
            print(f"  {_hr()}")
            for q in queries[:4]:
                print(f"  {DIM}›{RESET} {q}")
            print()

        # ── Retrieved code (if already available) ─────────────
        if retrieved_chunks:
            self.print_retrieved(retrieved_chunks)

        print(f"  {DIM}{_hr('─', 66)}{RESET}")
        print(f"  {DIM}Starting execution…{RESET}")
        print()

    def print_retrieved(
        self,
        chunks: List[Dict],
        max_chunks: int = 4,
        max_lines: int = 8,
    ) -> None:
        """Print a preview of the retrieved code chunks."""
        print(f"  {BOLD}Code I found{RESET}")
        print(f"  {_hr()}")

        seen = set()
        count = 0
        for chunk in chunks:
            key = (chunk.get("file"), chunk.get("name"))
            if key in seen:
                continue
            seen.add(key)
            count += 1
            if count > max_chunks:
                break

            file_name = chunk.get("file", "?")
            symbol    = chunk.get("name", "")
            sym_type  = chunk.get("type", "")
            code      = (chunk.get("code") or chunk.get("content") or "").strip()
            code_lines = code.splitlines()[:max_lines]

            label = f"{file_name}"
            if symbol:
                label += f" {DIM}::{RESET} {CYAN}{symbol}{RESET}"
            if sym_type:
                label += f"  {DIM}({sym_type}){RESET}"

            print(f"\n  {DIM}[{count}]{RESET} {label}")
            print(f"      {_hr('·', 60)}")
            for line in code_lines:
                print(f"      {DIM}{line}{RESET}")
            if len(code.splitlines()) > max_lines:
                remaining = len(code.splitlines()) - max_lines
                print(f"      {DIM}… {remaining} more lines{RESET}")
        print()

    # =========================================================
    # STEP ANNOUNCER
    # =========================================================

    def announce_step(self, tool: str, target: str = "") -> None:
        """Print a one-liner before each tool execution."""
        icons = {
            "semantic_retrieve":   "🔍",
            "modify_file":         "✏️ ",
            "repair_from_context": "🔧",
            "run_backend_tests":   "🧪",
            "run_frontend_build":  "📦",
            "run_frontend_tests":  "🧪",
            "rollback_file":       "⏪",
            "git_diff":            "📋",
            "analyze":             "🔎",
        }
        icon = icons.get(tool, "▶ ")
        target_str = f" {DIM}→ {target}{RESET}" if target else ""
        print(f"\n  {icon}  {BOLD}{tool}{RESET}{target_str}")


# =========================================================
# HELPERS
# =========================================================

def _wrap(text: str, width: int) -> List[str]:
    """Simple word wrapper."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= width:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
