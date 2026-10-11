# editing/patch_budget.py
from dataclasses import dataclass
import difflib

@dataclass
class PatchBudget:
    max_files: int = 1
    max_hunks: int = 2
    max_changed_lines: int = 30

    @classmethod
    def validate_patch(cls, original_content: str, patched_content: str, budget: "PatchBudget" = None) -> tuple[bool, str]:
        """
        Validates the proposed patched content against the patch budget.
        Returns (success, reason).
        """
        if budget is None:
            budget = cls()

        orig_lines = original_content.splitlines()
        pat_lines = patched_content.splitlines()

        diff = list(difflib.unified_diff(orig_lines, pat_lines, n=0))

        changed_lines = 0
        hunks = 0
        for line in diff:
            if line.startswith("@@"):
                hunks += 1
            elif line.startswith("+") and not line.startswith("+++"):
                changed_lines += 1
            elif line.startswith("-") and not line.startswith("---"):
                changed_lines += 1

        if changed_lines > budget.max_changed_lines:
            return False, f"Patch too large: changed lines ({changed_lines}) exceeds budget ({budget.max_changed_lines})"

        if hunks > budget.max_hunks:
            return False, f"Patch too fragmented: hunks ({hunks}) exceeds budget ({budget.max_hunks})"

        return True, "Validation passed"
