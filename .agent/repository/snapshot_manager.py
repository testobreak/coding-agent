# repository/snapshot_manager.py
#
# Repository Snapshot Isolation — the missing "repository time" abstraction.
#
# Every Local Cursor request must execute against a specific, named repository
# snapshot. A snapshot captures:
#
#   git_head   — current commit hash (deterministic for committed state)
#   dirty_hash — sha256 of the content of all modified/untracked files
#   snapshot_id — sha256(git_head + ":" + dirty_hash) — universal truth ref
#
# This is NOT just git state. It covers unsaved IDE buffers via the dirty_hash
# component, making it suitable for IDE-integrated Local Cursor.
#
# Design principles:
#   - Cheap to compute (<10ms for typical repos)
#   - Deterministic (same repo state → same snapshot_id)
#   - No false negatives (any file change → different snapshot_id)
#   - Degrades gracefully when git is unavailable
#
# Authority hierarchy:
#   Tier 0 (canonical):  disk files
#   Tier 1 (derived):    symbol graph, embeddings, dependency graph
#   Tier 2 (ephemeral):  task memory, retrieved chunks, spans

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class RepoSnapshot:
    """
    An immutable descriptor of a specific repository state.

    snapshot_id is the canonical truth reference — all derived intelligence
    (symbol graph, embeddings, task state) must be tagged with this ID
    to be considered valid for this snapshot.
    """
    git_head:    str          # Commit SHA or "no-git" / "dirty-only"
    dirty_hash:  str          # sha256 of modified file content (empty string if clean)
    snapshot_id: str          # sha256(git_head + ":" + dirty_hash)
    dirty_files: List[str]    # Paths of in-flight modified/untracked files
    computed_at: str          # ISO timestamp


@dataclass
class SnapshotValidationResult:
    """
    Result of comparing a stored snapshot_id against the current repo state.
    Returned by StateManager.validate_snapshot().
    """
    is_fresh:         bool          # True → snapshot matches, nothing to do
    stale_fields:     List[str]     # TaskState fields that must be cleared
    changed_files:    List[str]     # Files that changed since snapshot was taken
    current_snapshot: RepoSnapshot  # The freshly computed current snapshot


# Fields to clear when a task's snapshot is stale.
# Goal, plan, and modification_targets survive — only ephemeral runtime
# intelligence is invalidated.
STALE_FIELDS = [
    "retrieved_chunks",
    "active_symbols",
    "tool_outputs",
    "architecture_notes",
    "last_confidence",
    "execution_history",
    "reflections",
    "repair_history",
    "generated_code",
    "validation_results",
    "git_diff",
]


# ── SnapshotManager ───────────────────────────────────────────────────────────

class SnapshotManager:
    """
    Computes and manages repository snapshots.

    Usage:
        snap = SnapshotManager().current_snapshot(repo_root)
        if not SnapshotManager().snapshots_match(task.snapshot_id, snap.snapshot_id):
            # repo changed — invalidate ephemeral task state
    """

    def current_snapshot(self, repo_root: str = ".") -> RepoSnapshot:
        """
        Compute the current repository snapshot.

        Steps:
          1. Get git HEAD commit hash (fast — single git command).
          2. List dirty (modified + untracked) files via git status.
          3. Hash the *content* of those dirty files.
          4. Combine git_head + dirty_hash into snapshot_id.

        Falls back gracefully if git is unavailable.
        """
        repo_root = os.path.abspath(repo_root)
        git_head  = self._get_git_head(repo_root)
        dirty_files = self._get_dirty_files(repo_root)
        dirty_hash  = self._hash_dirty_files(repo_root, dirty_files)

        raw = f"{git_head}:{dirty_hash}"
        snapshot_id = hashlib.sha256(raw.encode()).hexdigest()[:16]

        return RepoSnapshot(
            git_head=git_head,
            dirty_hash=dirty_hash,
            snapshot_id=snapshot_id,
            dirty_files=dirty_files,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    def snapshots_match(self, a: str, b: str) -> bool:
        """True if two snapshot IDs represent the same repository state."""
        if not a or not b:
            return False
        return a == b

    def changed_files_since(
        self,
        old_snapshot: RepoSnapshot,
        repo_root: str = ".",
    ) -> List[str]:
        """
        Return list of files that have changed between old_snapshot and now.
        Used to produce a human-readable staleness summary.
        """
        current = self.current_snapshot(repo_root)
        if self.snapshots_match(old_snapshot.snapshot_id, current.snapshot_id):
            return []
        # Union of old dirty files and new dirty files — conservative
        changed = set(old_snapshot.dirty_files) | set(current.dirty_files)
        return sorted(changed)

    def build_validation_result(
        self,
        stored_snapshot_id: str,
        repo_root: str = ".",
    ) -> SnapshotValidationResult:
        """
        Compare stored_snapshot_id against the current repo state.
        Returns a SnapshotValidationResult describing what (if anything)
        must be invalidated in the task state.
        """
        current = self.current_snapshot(repo_root)

        if self.snapshots_match(stored_snapshot_id, current.snapshot_id):
            return SnapshotValidationResult(
                is_fresh=True,
                stale_fields=[],
                changed_files=[],
                current_snapshot=current,
            )

        # Determine which files changed (best-effort — uses current dirty list)
        changed = sorted(set(current.dirty_files))

        return SnapshotValidationResult(
            is_fresh=False,
            stale_fields=list(STALE_FIELDS),
            changed_files=changed,
            current_snapshot=current,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_git_head(self, repo_root: str) -> str:
        """Return current git commit SHA, or 'no-git' if git is unavailable."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "no-git"

    def _get_dirty_files(self, repo_root: str) -> List[str]:
        """
        Return relative paths of modified and untracked files.
        Includes both tracked-but-modified and new untracked files so that
        unsaved IDE additions are captured in the snapshot.
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode != 0:
                return []
            paths = []
            for line in result.stdout.splitlines():
                if len(line) < 4:
                    continue
                # Format: "XY filename" — strip status codes
                rel_path = line[3:].strip()
                # Handle renames: "old -> new"
                if " -> " in rel_path:
                    rel_path = rel_path.split(" -> ")[-1]
                paths.append(rel_path)
            return paths
        except Exception:
            return []

    def _hash_dirty_files(self, repo_root: str, dirty_files: List[str]) -> str:
        """
        SHA-256 hash of the combined content of all dirty files.
        Returns empty string if there are no dirty files (clean tree).
        """
        if not dirty_files:
            return ""

        hasher = hashlib.sha256()
        for rel_path in sorted(dirty_files):
            abs_path = os.path.join(repo_root, rel_path)
            hasher.update(rel_path.encode())          # include path in hash
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, "rb") as f:
                        while chunk := f.read(65536):
                            hasher.update(chunk)
                except OSError:
                    pass                              # deleted file — path hash enough
        return hasher.hexdigest()[:16]
