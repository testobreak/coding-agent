# parsers/base.py
#
# Shared data structures returned by every language parser.
#

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ClassSymbol:
    name:       str
    line_start: int
    line_end:   int
    parent:     Optional[str] = None   # outer class name (for nested classes)
    signature:  str = ""


@dataclass
class MethodSymbol:
    name:       str
    line_start: int
    line_end:   int
    parent:     Optional[str] = None   # enclosing class name
    signature:  str = ""


@dataclass
class InterfaceSymbol:
    name:       str
    line_start: int
    line_end:   int
    signature:  str = ""


@dataclass
class EnumSymbol:
    name:       str
    line_start: int
    line_end:   int
    signature:  str = ""


@dataclass
class ImportSymbol:
    name:       str
    line_start: int


@dataclass
class ParsedFile:
    classes:    List[ClassSymbol]     = field(default_factory=list)
    methods:    List[MethodSymbol]    = field(default_factory=list)
    interfaces: List[InterfaceSymbol] = field(default_factory=list)
    enums:      List[EnumSymbol]      = field(default_factory=list)
    imports:    List[ImportSymbol]    = field(default_factory=list)
    functions:  List[MethodSymbol]    = field(default_factory=list)  # top-level fns
    language:   str = ""
    error:      Optional[str] = None  # set if parsing failed


def node_text(node, src_bytes: bytes) -> str:
    """Extract UTF-8 text of a tree-sitter node."""
    return src_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
