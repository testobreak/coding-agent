# execution/patch_preview.py
#
# Speculative execution preview definitions and UX diff windows.

from dataclasses import dataclass

@dataclass
class PatchPreview:
    file_path: str
    old_content: str
    new_content: str
    unified_diff: str
    risk_score: float
    summary: str

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "old_content": self.old_content,
            "new_content": self.new_content,
            "unified_diff": self.unified_diff,
            "risk_score": self.risk_score,
            "summary": self.summary
        }


class DiffWindowBuilder:
    def build(self, content: str, start_line: int, end_line: int, padding: int = 20) -> str:
        """Extract a padding context window centered around the proposed edit span."""
        if not content:
            return ""
        lines = content.splitlines()
        # 1-indexed conversion to 0-indexed list slice boundaries
        start = max(0, start_line - 1 - padding)
        end = min(len(lines), end_line + padding)
        return "\n".join(lines[start:end])
