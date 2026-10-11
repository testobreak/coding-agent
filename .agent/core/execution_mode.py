# core/execution_mode.py
from enum import Enum

class ExecutionMode(Enum):
    AGENT = "agent"
    CURSOR = "cursor"

class CompatibleInt(int):
    def upper(self):
        mapping = {0: "INLINE", 1: "PATCH", 2: "ASSIST", 3: "AGENT", 4: "ANALYZE"}
        return mapping.get(self, "INLINE")

    def lower(self):
        mapping = {0: "inline", 1: "patch", 2: "assist", 3: "agent", 4: "analyze"}
        return mapping.get(self, "inline")

    def strip(self):
        return self.lower()

class TaskIntentMode(Enum):
    INLINE = CompatibleInt(0)   # tiny deterministic edits
    PATCH = CompatibleInt(1)    # symbol-aware edits
    ASSIST = CompatibleInt(2)   # explain / search
    AGENT = CompatibleInt(3)    # planner + repair loops
    ANALYZE = CompatibleInt(4)  # repository audit / review mode

    def __eq__(self, other):
        if isinstance(other, str):
            val = other.lower().replace("_", "")
            if val in ("inline", "inlineedit", "fastcompletion"):
                return self.value == 0
            if val in ("patch", "patchedit", "fastedit", "smartedit"):
                return self.value == 1
            if val in ("assist", "codeassist"):
                return self.value == 2
            if val in ("agent", "multifilepatch", "autonomousagent"):
                return self.value == 3
            if val in ("analyze", "analyse", "review", "audit"):
                return self.value == 4
        if isinstance(other, int):
            return self.value == other
        if isinstance(other, Enum):
            return self.value == other.value.value if hasattr(other.value, "value") else self.value == other.value
        return super().__eq__(other)

    def __hash__(self):
        return hash(self.value)

    def __str__(self):
        return self.name.lower()
