# repository_intelligence/workspace.py
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

class WorkspaceType(Enum):
    PYTHON = "python"
    NODE = "node"
    JAVA_MAVEN = "java_maven"
    JAVA_GRADLE = "java_gradle"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class Workspace:
    name: str
    root: Path
    type: WorkspaceType
