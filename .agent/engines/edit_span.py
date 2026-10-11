# engines/edit_span.py
"""Data class representing a precise edit location within a source file.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EditSpan:
    """Represents a precise edit location.

    Attributes:
        file_path: Absolute path to the file being edited.
        start_line: 1‑based start line number.
        end_line: 1‑based end line number.
        start_byte: Byte offset where the edit starts.
        end_byte: Byte offset where the edit ends.
        symbol_id: Optional identifier of the symbol (if available).
    """
    file_path: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    symbol_id: Optional[str] = None
