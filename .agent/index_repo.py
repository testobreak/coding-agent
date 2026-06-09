# index_repo.py
#
# One-stop runner:
#   python index_repo.py
#
# Does:
#   1. Ensure database exists
#   2. Apply schema
#   3. Scan repository -> populate files table
#   4. Index symbols  -> populate symbols table
#   5. Print verification queries
#
# Environment overrides (optional):
#   AGENT_DB_PASS=admin
#   AGENT_REPO_ROOT=d:\HRMS
#   AGENT_REPO_NAME=HRMS
#

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from db.connection import ensure_database, run_schema
from repository.scanner import RepositoryScanner
from indexing.symbol_indexer import SymbolIndexer
from db.connection import get_conn

# ── Configuration ─────────────────────────────────────────────
REPO_ROOT = os.getenv("AGENT_REPO_ROOT", r"d:\HRMS")
REPO_NAME = os.getenv("AGENT_REPO_NAME", "HRMS")


def main():
    print("\n" + "═" * 60)
    print("  Repository Intelligence Indexer")
    print("═" * 60)

    # ── Step 1: Database setup ────────────────────────────────
    print("\n[1/4] Ensuring database…")
    ensure_database()

    print("[2/4] Applying schema…")
    run_schema()

    # ── Step 2: Scan files ────────────────────────────────────
    print(f"\n[3/4] Scanning repository: {REPO_ROOT}")
    scanner = RepositoryScanner()
    repo_id = scanner.scan(repo_root=REPO_ROOT, repo_name=REPO_NAME)

    # ── Step 3: Index symbols ─────────────────────────────────
    print(f"\n[4/4] Indexing symbols…")
    indexer = SymbolIndexer()
    indexer.index_repository(repo_id)

    # ── Verification ─────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  VERIFICATION")
    print("═" * 60)

    with get_conn() as conn:
        with conn.cursor() as cur:

            # Q1: Files table
            cur.execute("SELECT COUNT(*) FROM files WHERE repository_id = %s", (repo_id,))
            file_count = cur.fetchone()[0]
            print(f"\n  files table:    {file_count:,} rows")

            # Q2: Symbol totals by type
            cur.execute("""
                SELECT symbol_type, COUNT(*)
                FROM   symbols
                WHERE  repository_id = %s
                GROUP  BY symbol_type
                ORDER  BY symbol_type
            """, (repo_id,))
            rows = cur.fetchall()
            print(f"  symbols table:")
            for sym_type, count in rows:
                print(f"    {sym_type:<12} {count:>6,}")

            total_symbols = sum(r[1] for r in rows)
            print(f"    {'TOTAL':<12} {total_symbols:>6,}")

            # Q3: Language breakdown
            cur.execute("""
                SELECT language, COUNT(*)
                FROM   files
                WHERE  repository_id = %s
                GROUP  BY language
                ORDER  BY COUNT(*) DESC
            """, (repo_id,))
            print(f"\n  Language breakdown:")
            for lang, count in cur.fetchall():
                print(f"    {lang:<14} {count:>5,} files")

    print("\n" + "═" * 60)
    print("  Sample queries you can run in psql:")
    print("═" * 60)
    print("""
  -- All files:
  SELECT relative_path, language, size_bytes FROM files LIMIT 20;

  -- Find a method:
  SELECT s.name, s.parent_name, f.relative_path, s.line_start
  FROM   symbols s JOIN files f ON s.file_id = f.id
  WHERE  s.name = 'createEmployee';

  -- All classes:
  SELECT name, parent_name, qualified_name, f.relative_path
  FROM   symbols s JOIN files f ON s.file_id = f.id
  WHERE  s.symbol_type = 'CLASS'
  ORDER  BY name;

  -- All interfaces:
  SELECT name, f.relative_path, s.line_start
  FROM   symbols s JOIN files f ON s.file_id = f.id
  WHERE  s.symbol_type = 'INTERFACE';
""")
    print("  ✅  Indexing complete.\n")


if __name__ == "__main__":
    main()
