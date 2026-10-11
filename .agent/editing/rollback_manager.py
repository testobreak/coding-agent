# editing/rollback_manager.py

import os
from typing import Dict, List, Optional

class RollbackManager:
    def __init__(self, file_manager):
        self.file_manager = file_manager
        self.snapshots: Dict[str, Optional[str]] = {}

    def snapshot(self, file_paths: List[str]) -> None:
        """
        Takes an in-memory snapshot of the specified files.
        Only stores the snapshot if we haven't already snapshotted the file in this transaction.
        """
        for path in file_paths:
            if path not in self.snapshots:
                content = self.file_manager.read_file(path)
                self.snapshots[path] = content

    def rollback(self) -> None:
        """
        Restores all files in the snapshot dictionary to their original content.
        """
        for path, content in self.snapshots.items():
            if content is not None:
                self.file_manager.write_file(path, content)
                print(f"[RollbackManager] Restored {path} from snapshot.")
            else:
                print(f"[RollbackManager] Cannot restore {path}: content was None.")

    def clear(self) -> None:
        """
        Clears the snapshots database.
        """
        self.snapshots.clear()
