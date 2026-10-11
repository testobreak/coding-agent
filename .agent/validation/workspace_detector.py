# validation/workspace_detector.py
from enum import Enum
from pathlib import Path

class WorkspaceType(Enum):
    JAVA_MAVEN = "java_maven"
    JAVA_GRADLE = "java_gradle"
    PYTHON = "python"
    NODE = "node"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"

class WorkspaceDetector:
    @staticmethod
    def detect(repo_root: Path) -> WorkspaceType:
        repo_root = Path(repo_root)
        markers = {
            "pom.xml": WorkspaceType.JAVA_MAVEN,
            "build.gradle": WorkspaceType.JAVA_GRADLE,
            "package.json": WorkspaceType.NODE,
            "pyproject.toml": WorkspaceType.PYTHON,
            "requirements.txt": WorkspaceType.PYTHON
        }
        
        detected_types = set()
        for filename, w_type in markers.items():
            if (repo_root / filename).exists():
                detected_types.add(w_type)
                
        # Also check subdirectories (max depth 2)
        try:
            for item in repo_root.glob("*/pom.xml"):
                detected_types.add(WorkspaceType.JAVA_MAVEN)
            for item in repo_root.glob("*/build.gradle"):
                detected_types.add(WorkspaceType.JAVA_GRADLE)
            for item in repo_root.glob("*/package.json"):
                detected_types.add(WorkspaceType.NODE)
            for item in repo_root.glob("*/pyproject.toml"):
                detected_types.add(WorkspaceType.PYTHON)
            for item in repo_root.glob("*/requirements.txt"):
                detected_types.add(WorkspaceType.PYTHON)
        except Exception:
            pass

        if len(detected_types) > 1:
            return WorkspaceType.HYBRID
        elif len(detected_types) == 1:
            return list(detected_types)[0]
        return WorkspaceType.UNKNOWN
