# ide/virtual_workspace.py

import os
from typing import Dict, Optional

class VirtualWorkspace:
    _instance: Optional["VirtualWorkspace"] = None
    
    def __init__(self):
        self.buffer_overrides: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> "VirtualWorkspace":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_buffer(self, path: str, content: str):
        # Store using normalized absolute path
        abs_path = os.path.abspath(path)
        self.buffer_overrides[abs_path] = content

    def clear_buffer(self, path: str):
        abs_path = os.path.abspath(path)
        if abs_path in self.buffer_overrides:
            del self.buffer_overrides[abs_path]

    def read_file(self, path: str) -> str:
        abs_path = os.path.abspath(path)
        if abs_path in self.buffer_overrides:
            return self.buffer_overrides[abs_path]
            
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def exists(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        if abs_path in self.buffer_overrides:
            return True
        return os.path.exists(abs_path)
