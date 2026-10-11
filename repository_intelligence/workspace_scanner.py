# repository_intelligence/workspace_scanner.py
from pathlib import Path
from typing import List
from repository_intelligence.workspace import Workspace, WorkspaceType

class WorkspaceScanner:
    def scan(self, repo_root: Path) -> List[Workspace]:
        workspaces = []
        try:
            self._scan_dir(repo_root, repo_root, workspaces)
        except Exception as e:
            print(f"[WorkspaceScanner] Scan error: {e}")
        return workspaces

    def _scan_dir(self, current_dir: Path, repo_root: Path, workspaces: List[Workspace], depth: int = 0):
        if depth > 3:
            return
            
        try:
            files = []
            subdirs = []
            for entry in current_dir.iterdir():
                if entry.is_file():
                    files.append(entry.name)
                elif entry.is_dir():
                    if entry.name not in [".git", "node_modules", "venv", ".venv", ".agent", ".cache", "dist", "build", "target"]:
                        subdirs.append(entry)
        except Exception:
            return

        has_pom = "pom.xml" in files
        has_gradle = "build.gradle" in files or "build.gradle.kts" in files
        has_package_json = "package.json" in files
        has_pyproject = "pyproject.toml" in files or "requirements.txt" in files

        workspace_type = None
        if has_pom:
            workspace_type = WorkspaceType.JAVA_MAVEN
        elif has_gradle:
            workspace_type = WorkspaceType.JAVA_GRADLE
        elif has_package_json:
            workspace_type = WorkspaceType.NODE
        elif has_pyproject:
            workspace_type = WorkspaceType.PYTHON

        if workspace_type:
            rel_path = current_dir.relative_to(repo_root)
            name = str(rel_path) if str(rel_path) != "." else "root"
            # Avoid duplicate workspace listings for the same directory
            if not any(w.root == current_dir for w in workspaces):
                workspaces.append(Workspace(
                    name=name,
                    root=current_dir,
                    type=workspace_type
                ))

        for subdir in subdirs:
            self._scan_dir(subdir, repo_root, workspaces, depth + 1)
