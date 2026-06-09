# retrieval/index_tracker.py
#
# Tracks SHA-256 hashes of all indexed source files.
# Saved to .cache/file_hashes.json alongside the FAISS index.
# Used by CodeRetriever to detect when the index is stale and
# needs a partial or full rebuild.
#

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from retrieval.chunker.chunk_utils import (
    IGNORE_DIRS,
    SUPPORTED_EXTENSIONS,
    MAX_FILE_SIZE_MB,
)

HASHES_FILE = os.path.join(".cache", "file_hashes.json")


class IndexTracker:
    """
    Manages file-hash state for the code index.

    Usage:
        tracker = IndexTracker()
        stale, added, removed, changed = tracker.diff(repo_root)
        if stale:
            rebuild_index(changed | added)
            tracker.save(repo_root)
    """

    def __init__(self):
        self.hashes: Dict[str, str] = {}  # {str(path): sha256_hex}

    # =========================================================
    # LOAD / SAVE
    # =========================================================

    def load(self) -> bool:
        """Load saved hashes. Returns True if file existed."""
        try:
            if os.path.exists(HASHES_FILE):
                with open(HASHES_FILE, "r", encoding="utf-8") as f:
                    self.hashes = json.load(f)
                return True
        except Exception as e:
            print(f"[IndexTracker] Could not load hashes: {e}")
        self.hashes = {}
        return False

    def save(self, repo_root: str) -> None:
        """Re-scan and save current file hashes."""
        self.hashes = self._scan(repo_root)
        try:
            os.makedirs(os.path.dirname(HASHES_FILE), exist_ok=True)
            with open(HASHES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.hashes, f, indent=2)
            print(f"[IndexTracker] Saved hashes for {len(self.hashes)} files.")
        except Exception as e:
            print(f"[IndexTracker] Could not save hashes: {e}")

    # =========================================================
    # DIFF
    # =========================================================

    def diff(
        self, repo_root: str
    ) -> Tuple[bool, Set[str], Set[str], Set[str]]:
        """
        Compare saved hashes against the current repo state.

        Returns:
            (is_stale, added_paths, removed_paths, changed_paths)
            is_stale is True if any of added/removed/changed is non-empty.
        """
        current = self._scan(repo_root)
        saved = self.hashes

        saved_keys = set(saved.keys())
        current_keys = set(current.keys())

        added = current_keys - saved_keys
        removed = saved_keys - current_keys
        changed = {
            k for k in (saved_keys & current_keys)
            if saved[k] != current[k]
        }

        is_stale = bool(added or removed or changed)

        if is_stale:
            print(
                f"[IndexTracker] Index stale — "
                f"added={len(added)}, removed={len(removed)}, "
                f"changed={len(changed)}"
            )
        else:
            print("[IndexTracker] Index is up-to-date.")

        return is_stale, added, removed, changed

    # =========================================================
    # SCAN
    # =========================================================

    def _scan(self, repo_root: str) -> Dict[str, str]:
        """Walk the repo and return {path_str: sha256} for all indexed files."""
        root = Path(repo_root)
        result: Dict[str, str] = {}

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if self._should_skip(path):
                continue
            try:
                h = self._hash_file(path)
                result[str(path)] = h
            except Exception:
                pass

        return result

    def _should_skip(self, path: Path) -> bool:
        if any(part in IGNORE_DIRS for part in path.parts):
            return True
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
            return size_mb > MAX_FILE_SIZE_MB
        except Exception:
            return True

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()
