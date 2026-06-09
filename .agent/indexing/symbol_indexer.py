# indexing/symbol_indexer.py
#
# Step 4 — Symbol Indexer
#
# Flow:
#   file (from DB)
#    ↓
#   parse with tree-sitter (via registry)
#    ↓
#   extract CLASS / METHOD / FUNCTION / INTERFACE / ENUM
#    ↓
#   upsert into symbols table
#
# This is separate from the scanner — you can re-index symbols
# without re-scanning file metadata.
#

import time
from typing import Optional

from db.connection import get_conn
from parsers.registry import registry
from parsers.base import ParsedFile


# Symbol type constants matching the DB CHECK constraint
CLASS     = "CLASS"
METHOD    = "METHOD"
FUNCTION  = "FUNCTION"
INTERFACE = "INTERFACE"
ENUM      = "ENUM"


class SymbolIndexer:
    """
    Reads files from the `files` table, parses each one,
    and populates the `symbols` table.
    """

    def __init__(self):
        self.indexed   = 0
        self.symbols   = 0
        self.skipped   = 0
        self.errors    = 0

    # =========================================================
    # MAIN — index an entire repository
    # =========================================================

    def index_repository(self, repo_id: int) -> None:
        """Index all parseable files for a repository."""
        files = self._get_files(repo_id)
        total = len(files)
        print(f"\n[Indexer] Indexing symbols for repo_id={repo_id} ({total} files)")

        start = time.time()

        for i, file_row in enumerate(files, 1):
            file_id   = file_row["id"]
            path      = file_row["path"]
            language  = file_row["language"]
            rel_path  = file_row["relative_path"]

            if (i % 50) == 0:
                print(f"[Indexer] {i}/{total}  symbols={self.symbols}")

            if not registry.supports(language):
                self.skipped += 1
                continue

            parsed = registry.parse_file(path, language)
            if parsed is None:
                self.skipped += 1
                continue

            if parsed.error:
                self.errors += 1
                continue

            # Delete old symbols for this file before re-inserting
            self._delete_file_symbols(file_id)

            # Build rows for bulk insert
            rows = self._build_rows(parsed, file_id, repo_id, rel_path, language)
            if rows:
                self._insert_symbols(rows)
                self.symbols += len(rows)

            self.indexed += 1

        elapsed = time.time() - start
        print(
            f"[Indexer] Done in {elapsed:.2f}s — "
            f"{self.indexed} files parsed, {self.symbols} symbols, "
            f"{self.skipped} skipped, {self.errors} errors"
        )

    # =========================================================
    # BUILD SYMBOL ROWS
    # =========================================================

    def _build_rows(
        self,
        parsed: ParsedFile,
        file_id: int,
        repo_id: int,
        rel_path: str,
        language: str,
    ) -> list:
        rows = []

        # ── Classes ──────────────────────────────────────────
        for sym in parsed.classes:
            rows.append((
                file_id, repo_id,
                sym.name,
                self._qualified(rel_path, sym.parent, sym.name),
                CLASS,
                sym.parent,
                sym.line_start, sym.line_end,
                sym.signature or sym.name,
                language,
            ))

        # ── Interfaces ────────────────────────────────────────
        for sym in parsed.interfaces:
            rows.append((
                file_id, repo_id,
                sym.name,
                self._qualified(rel_path, None, sym.name),
                INTERFACE,
                None,
                sym.line_start, sym.line_end,
                sym.signature or sym.name,
                language,
            ))

        # ── Enums ─────────────────────────────────────────────
        for sym in parsed.enums:
            rows.append((
                file_id, repo_id,
                sym.name,
                self._qualified(rel_path, None, sym.name),
                ENUM,
                None,
                sym.line_start, sym.line_end,
                sym.signature or sym.name,
                language,
            ))

        # ── Methods (inside classes) ──────────────────────────
        for sym in parsed.methods:
            rows.append((
                file_id, repo_id,
                sym.name,
                self._qualified(rel_path, sym.parent, sym.name),
                METHOD,
                sym.parent,
                sym.line_start, sym.line_end,
                sym.signature or sym.name,
                language,
            ))

        # ── Top-level functions ───────────────────────────────
        for sym in parsed.functions:
            rows.append((
                file_id, repo_id,
                sym.name,
                self._qualified(rel_path, None, sym.name),
                FUNCTION,
                None,
                sym.line_start, sym.line_end,
                sym.signature or sym.name,
                language,
            ))

        return rows

    # =========================================================
    # DB OPERATIONS
    # =========================================================

    def _get_files(self, repo_id: int) -> list:
        sql = """
            SELECT id, path, relative_path, language
            FROM   files
            WHERE  repository_id = %s
            ORDER  BY id
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (repo_id,))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _delete_file_symbols(self, file_id: int) -> None:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM symbols WHERE file_id = %s", (file_id,))

    def _insert_symbols(self, rows: list) -> None:
        sql = """
            INSERT INTO symbols
                (file_id, repository_id, name, qualified_name,
                 symbol_type, parent_name,
                 line_start, line_end, signature, language)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _qualified(rel_path: str, parent: Optional[str], name: str) -> str:
        """
        Build a qualified name from file path + parent class + symbol name.
        e.g. src/EmployeeService.java + EmployeeService + createEmployee
          -> EmployeeService.createEmployee
        """
        if parent:
            return f"{parent}.{name}"
        return name
