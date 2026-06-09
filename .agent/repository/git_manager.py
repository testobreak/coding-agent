# repository/git_manager.py

import subprocess
from pathlib import Path
from typing import Optional


class GitManager:

    def __init__(
        self,
        root="."
    ):

        self.root = Path(root)

    # =====================================================
    # STATUS
    # =====================================================

    def status(self):

        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        return result.stdout

    # =====================================================
    # DIFF
    # =====================================================

    def diff(self, path: str = None):
        cmd = ["git", "diff"]
        if path:
            cmd.extend(["--", path])
        else:
            cmd.extend(["--", ":(exclude).agent"])

        result = subprocess.run(
            cmd,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        return result.stdout

    # =====================================================
    # CURRENT BRANCH
    # =====================================================

    def current_branch(self):

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        return result.stdout.strip()

    # =====================================================
    # LAST COMMIT
    # =====================================================

    def last_commit(self):

        result = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        return result.stdout.strip()

    # =====================================================
    # CHECKPOINT
    # =====================================================

    def create_checkpoint(
        self,
        message: str = "agent checkpoint"
    ) -> Optional[str]:
        """
        Creates a lightweight stash-based recovery point before modifications.

        Uses `git stash push --include-untracked` instead of git commit so that
        the main git log is not polluted with dozens of checkpoint commits during
        long autonomous runs.

        Returns the stash ref string (e.g. "stash@{0}") on success, or None if
        the working tree is clean (nothing to stash) or on any error.
        """
        try:

            result = subprocess.run(
                [
                    "git",
                    "stash",
                    "push",
                    "--include-untracked",
                    "-m",
                    message
                ],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            if result.returncode != 0:
                return None

            # "No local changes to save" means tree was clean — that is fine
            if "No local changes to save" in result.stdout:
                return None

            # Restore the stash immediately so the working tree looks unchanged
            # (we only want the snapshot, not to clear the working dir)
            subprocess.run(
                ["git", "stash", "apply"],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            return "stash@{0}"

        except Exception:
            return None

    def restore_checkpoint(
        self,
        stash_ref: str = "stash@{0}"
    ) -> bool:
        """
        Restores working tree from a stash-based checkpoint.
        Drops the stash entry after a successful pop.
        """
        try:

            result = subprocess.run(
                ["git", "stash", "pop"],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            return result.returncode == 0

        except Exception:
            return False

    # =====================================================
    # COMMIT
    # =====================================================

    def commit(
        self,
        message: str
    ) -> bool:
        """
        Stages all untracked/modified files and runs a git commit.
        """
        try:

            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.root,
                check=True
            )

            result = subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    message
                ],
                cwd=self.root,
                capture_output=True,
                text=True
            )

            return result.returncode == 0

        except Exception:
            return False

    # =====================================================
    # ROLLBACK FILE
    # =====================================================

    def rollback_file(
        self,
        file_path: str
    ) -> bool:
        """
        Reverts modifications to a single specified target file.
        """
        try:

            subprocess.run(
                [
                    "git",
                    "restore",
                    file_path
                ],
                cwd=self.root,
                check=True
            )

            return True

        except Exception:
            return False

    # =====================================================
    # ROLLBACK TO COMMIT
    # =====================================================

    def rollback_to_commit(
        self,
        commit_hash: str
    ) -> bool:
        """
        Performs a full hard reset to a specific previous commit anchor.
        """
        try:

            subprocess.run(
                [
                    "git",
                    "reset",
                    "--hard",
                    commit_hash
                ],
                cwd=self.root,
                check=True
            )

            return True

        except Exception:
            return False
