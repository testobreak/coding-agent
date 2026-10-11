# execution/context_engine.py
import json
from pathlib import Path
from typing import List, Optional
from repository_intelligence.workspace import Workspace, WorkspaceType
from repository_intelligence.workspace_scanner import WorkspaceScanner
from execution.workspace_resolver import WorkspaceResolver
from execution.tool_router import ToolRouter

class WorkspaceRoutingError(Exception):
    pass

class ExecutionContextEngine:
    def __init__(self, repo_root="."):
        self.repo_root = Path(repo_root).resolve()
        self.metadata_path = self.repo_root / ".agent" / "workspaces_metadata.json"
        self.workspaces = []
        self._load_or_scan_workspaces()
        self.resolver = WorkspaceResolver(self.workspaces)
        self.tool_router = ToolRouter()

    def _load_or_scan_workspaces(self):
        # Load from cache file
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("workspaces", []):
                        self.workspaces.append(Workspace(
                            name=item["name"],
                            root=self.repo_root / item["root"],
                            type=WorkspaceType(item["type"])
                        ))
                return
            except Exception:
                pass

        # Scan repository if no cache exists
        scanner = WorkspaceScanner()
        self.workspaces = scanner.scan(self.repo_root)
        
        # Persist cached workspaces to metadata
        try:
            self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump({
                    "workspaces": [
                        {
                            "name": w.name,
                            "root": str(w.root.relative_to(self.repo_root)) if w.root != self.repo_root else ".",
                            "type": w.type.value
                        }
                        for w in self.workspaces
                    ]
                }, f, indent=2)
        except Exception as e:
            print(f"[ExecutionContextEngine] Caching failed: {e}")

    def resolve_workspace(self, file_path: str) -> Workspace:
        """
        Resolves workspace for the given file. Fails fast if no workspace found.
        """
        workspace = self.resolver.resolve_for_file(file_path)
        if not workspace:
            raise WorkspaceRoutingError(f"No workspace found for target file: {file_path}")
        return workspace

    def build_command_for_file(self, file_path: str, action: str) -> tuple[list[str], Path]:
        """
        Builds the correct command list and absolute working directory for a file-centric action.
        """
        workspace = self.resolve_workspace(file_path)
        cmd = self.tool_router.build_command(workspace, action)
        return cmd, workspace.root
