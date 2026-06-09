# editing/patch.py
#
# Patch and PatchSet models representing localized surgical updates.

from dataclasses import dataclass, field
from typing import List

@dataclass
class Patch:
    symbol_fqn: str
    file_path: str
    old_text: str
    new_text: str
    patch_block: str  # The SEARCH/REPLACE diff text block

@dataclass
class PatchSet:
    patches: List[Patch] = field(default_factory=list)
