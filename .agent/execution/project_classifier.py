# execution/project_classifier.py
from enum import Enum
from pathlib import Path
from dataclasses import dataclass
from typing import List

class ProjectType(Enum):
    PYTHON = "python"
    JAVA_MAVEN = "java_maven"
    JAVA_GRADLE = "java_gradle"
    NODE = "node"
    MONOREPO = "monorepo"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class ProjectUnit:
    root: str
    type: ProjectType

class ProjectClassifier:
    def detect(self, repo_root: Path) -> ProjectType:
        units = self.detect_subprojects(repo_root)
        if not units:
            return ProjectType.UNKNOWN
        if len(units) > 1:
            return ProjectType.MONOREPO
        return units[0].type

    def detect_subprojects(self, repo_root: Path) -> List[ProjectUnit]:
        units = []
        # Check root directory first
        self._check_dir(repo_root, "", units)
        
        # Check immediate subdirectories
        try:
            for p in repo_root.iterdir():
                if p.is_dir() and p.name not in [".git", "node_modules", "venv", ".venv", ".agent", ".cache"]:
                    # Prevent duplicate check if root was already identified
                    rel_path = p.name
                    self._check_dir(p, rel_path, units)
        except Exception:
            pass
            
        return units

    def _check_dir(self, directory: Path, rel_path: str, units: List[ProjectUnit]):
        files = []
        try:
            files = [f.name for f in directory.iterdir() if f.is_file()]
        except Exception:
            return
            
        has_pom = "pom.xml" in files
        has_gradle = "build.gradle" in files or "build.gradle.kts" in files
        has_requirements = "requirements.txt" in files
        has_pyproject = "pyproject.toml" in files
        has_package_json = "package.json" in files

        # Avoid double adding same directory
        if any(u.root == rel_path for u in units):
            return

        if has_pom:
            units.append(ProjectUnit(rel_path, ProjectType.JAVA_MAVEN))
        elif has_gradle:
            units.append(ProjectUnit(rel_path, ProjectType.JAVA_GRADLE))
        elif has_package_json:
            units.append(ProjectUnit(rel_path, ProjectType.NODE))
        elif has_requirements or has_pyproject:
            units.append(ProjectUnit(rel_path, ProjectType.PYTHON))
