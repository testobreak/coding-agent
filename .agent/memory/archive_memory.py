# memory/archive_memory.py

from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class ArchiveMemory:
    tool_outputs: List[Dict[str, Any]] = field(default_factory=list)
    raw_logs: List[str] = field(default_factory=list)
