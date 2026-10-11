# repository_intelligence/indexer/file_classifier.py

from enum import Enum
from dataclasses import dataclass
from pathlib import Path

class FileRole(str, Enum):
    SOURCE = "source"
    TEST = "test"
    GENERATED = "generated"
    BUILD_ARTIFACT = "build_artifact"
    CONFIG = "config"
    DOC = "doc"
    AGENT_STATE = "agent_state"
    BINARY = "binary"
    CACHE = "cache"

@dataclass
class IndexDecision:
    include: bool
    reason: str
    role: FileRole
    priority: float

class FileClassifier:
    @staticmethod
    def classify(filepath: Path, root: Path) -> IndexDecision:
        try:
            relative = filepath.relative_to(root)
        except ValueError:
            return IndexDecision(include=False, reason="Out of root boundary", role=FileRole.BUILD_ARTIFACT, priority=0.0)

        parts = [p.lower() for p in relative.parts]
        suffix = filepath.suffix.lower()

        # 1. Agent internals
        if ".agent" in parts:
            return IndexDecision(include=False, reason="Agent state", role=FileRole.AGENT_STATE, priority=0.0)

        # 2. Build artifacts and temp dirs
        build_dirs = {"target", "dist", "build", "out", "bin", "obj", ".gradle", ".mvn", ".idea", ".vscode", "node_modules", "__pycache__"}
        if any(part in build_dirs for part in parts):
            return IndexDecision(include=False, reason="Build artifact directory", role=FileRole.BUILD_ARTIFACT, priority=0.0)

        blocked_exts = {".class", ".log", ".xml", ".dumpstream", ".pyc", ".pyo", ".pyd", ".map", ".min.js", ".jar", ".war"}
        if suffix in blocked_exts:
            return IndexDecision(include=False, reason="Blocked build artifact extension", role=FileRole.BUILD_ARTIFACT, priority=0.0)

        # 3. Generated code check
        from repository_intelligence.indexer.file_discovery import is_generated_source
        if is_generated_source(filepath) or any(part in ("generated", "generated-sources", "apt-generated") for part in parts):
            return IndexDecision(include=False, reason="Generated code", role=FileRole.GENERATED, priority=0.0)

        # 4. Config files
        config_exts = {".json", ".yaml", ".yml", ".properties", ".toml", ".ini", ".conf"}
        if suffix in config_exts:
            return IndexDecision(include=True, reason="Editable config file", role=FileRole.CONFIG, priority=0.8)

        # 5. Documentation
        doc_exts = {".md", ".txt", ".pdf"}
        if suffix in doc_exts:
            return IndexDecision(include=True, reason="Project documentation", role=FileRole.DOC, priority=0.5)

        # 6. Tests
        if any("test" in part for part in parts) or "tests" in parts or "src/test" in filepath.as_posix().lower():
            return IndexDecision(include=True, reason="Test source file", role=FileRole.TEST, priority=0.35)

        # 7. Source files (Main edit targets)
        source_exts = {".py", ".java", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".cpp", ".c", ".h", ".cs", ".kt", ".rb"}
        if suffix in source_exts:
            # Check if it belongs to a main source dir (backend/src/main/ or frontend/src/ or similar)
            is_main = "src/main" in filepath.as_posix() or "frontend/src" in filepath.as_posix() or "src" in parts
            priority = 1.0 if is_main else 0.8
            return IndexDecision(include=True, reason="Canonical source file", role=FileRole.SOURCE, priority=priority)

        return IndexDecision(include=False, reason="Unknown file type", role=FileRole.BINARY, priority=0.0)
