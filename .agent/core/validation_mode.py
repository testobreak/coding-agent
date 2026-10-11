# core/validation_mode.py
from enum import Enum

class ValidationMode(Enum):
    NONE = 0
    FAST = 1
    SEMANTIC = 2
    COMPILE = 3
    FULL = 4

class ValidationState(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
