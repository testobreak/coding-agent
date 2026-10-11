# repository_intelligence/manifest/models.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any

@dataclass
class FileRecord:
    path: str
    language: str
    module: str
    file_type: str
    symbol_count: int
    hash: str
    size_bytes: int
    indexed_at: str  # ISO format string

@dataclass
class ModuleRecord:
    name: str
    root_path: str
    language: str
    dependencies: List[str] = field(default_factory=list)

@dataclass
class RepositoryManifest:
    files_by_path: Dict[str, FileRecord] = field(default_factory=dict)
    files_by_module: Dict[str, List[FileRecord]] = field(default_factory=dict)
    files_by_language: Dict[str, List[FileRecord]] = field(default_factory=dict)
    files_by_symbol: Dict[str, List[FileRecord]] = field(default_factory=dict)
    modules: Dict[str, ModuleRecord] = field(default_factory=dict)
