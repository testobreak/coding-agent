# runtime/diff_printer.py
#
# Shows a coloured unified diff after every file modification.
#
# Output looks like:
#
#   ┌─────────────────────────────────────────────────────────────┐
#   │  PATCH APPLIED  EmployeeService.java                        │
#   └─────────────────────────────────────────────────────────────┘
#
#   @@ -42,7 +42,7 @@
#       public double calculateSalary(Employee emp) {
#   -       return emp.getSalary() - deductions;
#   +       return emp.getSalary() - (deductions != null ? deductions : 0.0);
#       }
#
#   ✓  1 file changed · 1 insertion · 1 deletion
#

import difflib
from pathlib import Path
from typing import Optional


RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
WHITE  = "\033[97m"


class DiffPrinter:
    """
    Prints a human-readable coloured diff after a file is patched.

    Usage:
        printer = DiffPrinter()
        printer.print_diff(original_content, modified_content, file_path)
    """

    MAX_DIFF_LINES = 120   # don't flood terminal on huge diffs

    # =========================================================
    # MAIN
    # =========================================================

    def print_diff(
        self,
        original: str,
        modified: str,
        file_path: str,
        success: bool = True,
    ) -> None:
        """
        Compute and print the diff between original and modified content.
        """
        if not original or not modified:
            return
        if original == modified:
            print(f"\n  {DIM}(no changes){RESET}")
            return

        filename = Path(file_path).name

        # Header
        status_icon = "✅" if success else "❌"
        status_word = "PATCH APPLIED" if success else "PATCH FAILED — ROLLED BACK"
        colour      = GREEN if success else RED
        print()
        print(
            f"  ┌{'─' * 64}┐\n"
            f"  │  {colour}{BOLD}{status_word}{RESET}  "
            f"{YELLOW}{filename}{RESET}"
            f"{' ' * max(0, 43 - len(status_word) - len(filename))}│\n"
            f"  └{'─' * 64}┘"
        )
        print()

        # Compute unified diff
        orig_lines = original.splitlines(keepends=True)
        mod_lines  = modified.splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
            n=3,       # 3 lines of context
        ))

        if not diff:
            print(f"  {DIM}(diff empty — whitespace-only change){RESET}")
            return

        # Print coloured diff (cap at MAX_DIFF_LINES)
        printed = 0
        for line in diff:
            if printed >= self.MAX_DIFF_LINES:
                remaining = len(diff) - printed
                print(f"\n  {DIM}… {remaining} more diff lines (truncated){RESET}")
                break

            self._print_line(line)
            printed += 1

        # Summary footer
        insertions = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        deletions  = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        print()
        if success:
            print(
                f"  {GREEN}✓{RESET}  1 file changed  "
                f"{GREEN}+{insertions} insertion{'s' if insertions != 1 else ''}{RESET}  "
                f"{RED}-{deletions} deletion{'s' if deletions != 1 else ''}{RESET}"
            )
        else:
            print(f"  {RED}✗  patch rolled back — file unchanged{RESET}")
        print()

    def print_rollback(self, file_path: str) -> None:
        """Print a rollback notification."""
        filename = Path(file_path).name
        print(
            f"\n  {RED}⏪  ROLLED BACK{RESET}  {YELLOW}{filename}{RESET}"
            f"  {DIM}(restored to last clean commit){RESET}\n"
        )

    # =========================================================
    # LINE PRINTER
    # =========================================================

    def _print_line(self, line: str) -> None:
        """Print one diff line with appropriate colour."""
        if line.startswith("@@"):
            # Hunk header — show in cyan
            print(f"  {CYAN}{line}{RESET}")
        elif line.startswith("+++") or line.startswith("---"):
            # File headers — dim
            print(f"  {DIM}{line}{RESET}")
        elif line.startswith("+"):
            # Addition — green
            print(f"  {GREEN}{line}{RESET}")
        elif line.startswith("-"):
            # Deletion — red
            print(f"  {RED}{line}{RESET}")
        else:
            # Context — dim
            print(f"  {DIM}{line}{RESET}")

    # =========================================================
    # PATCH SUMMARY (for multi-file operations)
    # =========================================================

    def print_summary(self, results: list) -> None:
        """
        Print a summary table after multiple files are modified.
        results: [{"path": str, "success": bool, "insertions": int, "deletions": int}, ...]
        """
        if not results:
            return

        print(f"\n  {BOLD}Modification Summary{RESET}")
        print(f"  {'─' * 64}")
        for r in results:
            icon   = f"{GREEN}✓{RESET}" if r.get("success") else f"{RED}✗{RESET}"
            path   = r.get("path", "?")
            ins    = r.get("insertions", 0)
            dels   = r.get("deletions", 0)
            print(
                f"  {icon}  {YELLOW}{Path(path).name:<40}{RESET}"
                f"  {GREEN}+{ins}{RESET}  {RED}-{dels}{RESET}"
            )
        print()
