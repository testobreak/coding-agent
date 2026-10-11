# execution/workspace_resolver.py
from pathlib import Path
from typing import List, Optional
from repository_intelligence.workspace import Workspace

class WorkspaceResolver:
    def __init__(self, workspaces: List[Workspace]):
        self.workspaces = workspaces

    def resolve_for_file(self, file_path: str) -> Optional[Workspace]:
        """
        Resolves the deepest enclosing workspace for a given file path.
        """
        best = None
        best_depth = -1
        
        # Ensure we have absolute paths for comparison
        file_path_obj = Path(file_path).resolve()

        for ws in self.workspaces:
            ws_root_resolved = ws.root.resolve()
            try:
                # This check raises ValueError if file_path_obj is not under ws_root_resolved
                file_path_obj.relative_to(ws_root_resolved)
                depth = len(ws_root_resolved.parts)
                if depth > best_depth:
                    best = ws
                    best_depth = depth
            except ValueError:
                pass

        return best
