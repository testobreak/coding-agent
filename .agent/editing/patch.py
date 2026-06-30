# editing/patch.py
from dataclasses import dataclass, field
from enum import Enum
from typing import List
from difflib import unified_diff

class PatchType(Enum):
    REPLACE = "replace"
    INSERT = "insert"
    DELETE = "delete"

@dataclass
class FilePatch:
    file_path: str
    patch_type: PatchType
    start_line: int
    end_line: int
    old_text: str
    new_text: str

@dataclass
class PatchSet:
    patches: List[FilePatch] = field(default_factory=list)

# Legacy Patch class for backward compatibility
@dataclass
class Patch:
    symbol_fqn: str
    file_path: str
    old_text: str
    new_text: str
    patch_block: str = ""
    operations: list = field(default_factory=list)

# Legacy PatchEdit class for backward compatibility
@dataclass
class PatchEdit:
    file_path: str
    start_line: int
    end_line: int
    replacement: str

class PatchFormatter:
    @staticmethod
    def to_unified_diff(patchset: PatchSet) -> str:
        diffs = []
        for patch in patchset.patches:
            diff = unified_diff(
                patch.old_text.splitlines(),
                patch.new_text.splitlines(),
                fromfile=patch.file_path,
                tofile=patch.file_path,
                lineterm=""
            )
            diffs.append("\n".join(diff))
        return "\n\n".join(diffs)
