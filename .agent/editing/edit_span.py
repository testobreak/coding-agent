# editing/edit_span.py
from dataclasses import dataclass

@dataclass
class EditSpan:
    file: str
    start_line: int
    end_line: int
    surrounding_context: str
    confidence: float
