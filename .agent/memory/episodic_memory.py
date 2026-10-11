# memory/episodic_memory.py

from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class EpisodicMemory:
    failed_attempts: List[str] = field(default_factory=list)
    summaries: List[Dict[str, Any]] = field(default_factory=list)
    reflections: List[str] = field(default_factory=list)

    test_failures: List[str] = field(default_factory=list)
    repair_history: List[Dict[str, Any]] = field(default_factory=list)
