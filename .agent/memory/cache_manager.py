# memory/cache_manager.py
"""
Simple in‑memory cache for file contents.
Used by ContextBuilder to avoid repeated disk I/O for the same file during a request.
"""

from threading import Lock
import os

class FileContentCache:
    _instance = None
    _lock = Lock()

    @classmethod
    def get_instance(cls):
        """Thread‑safe singleton accessor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        # Mapping of absolute path -> file content (str)
        self._cache = {}
        self._cache_lock = Lock()

    def get_file_content(self, path: str) -> str:
        """Return the content of *path*.
        The *path* may be absolute or relative to the repository root.
        Content is read once and stored in memory for the lifetime of the process.
        """
        # Resolve to absolute path for a stable key
        abs_path = os.path.abspath(path)
        with self._cache_lock:
            if abs_path in self._cache:
                return self._cache[abs_path]
            # Load from disk
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self._cache[abs_path] = content
                return content
            except Exception as e:
                # Store empty string to avoid repeated failed attempts
                self._cache[abs_path] = ""
                raise e
