# repository/scanner.py
#
# Step 2 — Repository Scanner
#
# Walks the repository directory tree, detects language from file extension,
# computes SHA-256 hash, and upserts one row per file into PostgreSQL.
#
# No parsing happens here — this is purely file metadata.
#
# Usage:
#   from repository.scanner import RepositoryScanner
#   scanner = RepositoryScanner(db_conn_factory=get_conn)
#   repo_id = scanner.scan(repo_root="d:/HRMS", repo_name="HRMS")
#

import os
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from db.connection import get_conn

# ── Language detection by extension ──────────────────────────
EXT_TO_LANGUAGE = {
    ".java":  "java",
    ".py":    "python",
    ".js":    "javascript",
    ".jsx":   "javascript",
    ".ts":    "typescript",
    ".tsx":   "typescript",
    ".kt":    "kotlin",
    ".go":    "go",
    ".rs":    "rust",
    ".cs":    "csharp",
    ".cpp":   "cpp",
    ".c":     "c",
    ".h":     "c",
    ".hpp":   "cpp",
    ".rb":    "ruby",
    ".php":   "php",
    ".swift": "swift",
    ".sql":   "sql",
    ".yaml":  "yaml",
    ".yml":   "yaml",
    ".json":  "json",
    ".xml":   "xml",
    ".html":  "html",
    ".css":   "css",
    ".scss":  "scss",
    ".md":    "markdown",
    ".sh":    "shell",
    ".bat":   "shell",
    ".ps1":   "powershell",
}

# ── Skip directories (never worth scanning) ──────────────────
SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg",
    "target",           # Maven build output
    "build",            # Gradle / npm build output
    "dist",             # Frontend dist
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv", "venv", "env",
    ".idea", ".vscode",
    ".agent",           # our own agent directory
    ".cache",
}

# ── Skip file extensions (binary / irrelevant) ────────────────
SKIP_EXTENSIONS = {
    ".class", ".jar", ".war", ".ear",
    ".pyc", ".pyo",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".rar",
    ".exe", ".dll", ".so", ".dylib",
    ".pdf", ".docx", ".xlsx",
    ".lock",   # package-lock.json, yarn.lock, etc.
}

MAX_FILE_SIZE = 2 * 1024 * 1024   # skip files > 2 MB


class RepositoryScanner:
    """
    Scans a repository root and populates the `repositories` and `files` tables.
    """

    def __init__(self):
        self.scanned = 0
        self.skipped = 0
        self.errors  = 0

    # =========================================================
    # MAIN
    # =========================================================

    def scan(
        self,
        repo_root: str,
        repo_name: str = None,
    ) -> int:
        """
        Walk repo_root, upsert all source files into PostgreSQL.
        Returns the repository_id.
        """
        repo_root = str(Path(repo_root).resolve())
        repo_name = repo_name or Path(repo_root).name

        print(f"\n[Scanner] Scanning: {repo_root}")
        print(f"[Scanner] Name:     {repo_name}")

        start = time.time()

        # 1. Upsert repository row
        repo_id = self._upsert_repository(repo_root, repo_name)
        print(f"[Scanner] Repository ID: {repo_id}")

        # 2. Walk and upsert files
        batch = []
        for root, dirs, files in os.walk(repo_root):
            # Prune skip dirs in-place (modifies dirs to stop os.walk descending)
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for filename in files:
                full_path = os.path.join(root, filename)
                result = self._process_file(full_path, repo_root, repo_id)
                if result:
                    batch.append(result)
                    # Flush in batches of 200
                    if len(batch) >= 200:
                        self._upsert_files(batch)
                        batch.clear()

        # Flush remainder
        if batch:
            self._upsert_files(batch)

        elapsed = time.time() - start
        print(
            f"[Scanner] Done in {elapsed:.2f}s — "
            f"{self.scanned} indexed, {self.skipped} skipped, {self.errors} errors"
        )
        return repo_id

    # =========================================================
    # PROCESS ONE FILE
    # =========================================================

    def _process_file(
        self,
        full_path: str,
        repo_root: str,
        repo_id: int,
    ) -> Optional[dict]:
        """Return a file record dict, or None if the file should be skipped."""
        path = Path(full_path)
        ext  = path.suffix.lower()

        if ext in SKIP_EXTENSIONS:
            self.skipped += 1
            return None

        try:
            stat = path.stat()
        except OSError:
            self.errors += 1
            return None

        if stat.st_size > MAX_FILE_SIZE:
            self.skipped += 1
            return None

        # SHA-256 hash of file content
        try:
            file_hash = self._hash_file(full_path)
        except OSError:
            self.errors += 1
            return None

        language = EXT_TO_LANGUAGE.get(ext, "other")
        relative = str(path.relative_to(repo_root)).replace("\\", "/")
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        self.scanned += 1
        return {
            "repository_id": repo_id,
            "path":          full_path,
            "relative_path": relative,
            "language":      language,
            "file_hash":     file_hash,
            "size_bytes":    stat.st_size,
            "modified_at":   modified,
        }

    # =========================================================
    # DB OPERATIONS
    # =========================================================

    def _upsert_repository(self, root_path: str, name: str) -> int:
        sql = """
            INSERT INTO repositories (name, root_path, indexed_at, updated_at)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT (root_path)
            DO UPDATE SET name=EXCLUDED.name, updated_at=NOW()
            RETURNING id
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (name, root_path))
                return cur.fetchone()[0]

    def _upsert_files(self, records: list) -> None:
        sql = """
            INSERT INTO files
                (repository_id, path, relative_path, language,
                 file_hash, size_bytes, modified_at, indexed_at)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (repository_id, relative_path)
            DO UPDATE SET
                path        = EXCLUDED.path,
                language    = EXCLUDED.language,
                file_hash   = EXCLUDED.file_hash,
                size_bytes  = EXCLUDED.size_bytes,
                modified_at = EXCLUDED.modified_at,
                indexed_at  = NOW()
        """
        rows = [
            (
                r["repository_id"],
                r["path"],
                r["relative_path"],
                r["language"],
                r["file_hash"],
                r["size_bytes"],
                r["modified_at"],
            )
            for r in records
        ]
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
