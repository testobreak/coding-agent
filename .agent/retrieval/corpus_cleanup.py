"""
retrieval/corpus_cleanup.py
===========================
One-shot script to evict contaminated rows from the indexing database.

Run once after deploying the corpus_filter module to purge file/symbol/embedding
rows whose paths are ineligible (build artifacts, agent internals, generated output).

Usage:
    cd .agent
    python -m retrieval.corpus_cleanup

Dry-run (shows counts but makes no changes):
    python -m retrieval.corpus_cleanup --dry-run
"""

import sys
import argparse
from pathlib import Path

# Ensure agent root is on sys.path
AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


def run_cleanup(dry_run: bool = False):
    from repository_intelligence.db.connection import SessionLocal
    from repository_intelligence.models.file import File
    from repository_intelligence.models.symbol import Symbol, Embedding, SymbolRelationship
    from retrieval.corpus_filter import is_corpus_eligible

    session = SessionLocal()
    try:
        print("\n[CorpusCleanup] Scanning index DB for ineligible files...")

        all_files = session.query(File).all()
        total = len(all_files)
        bad_file_ids = [f.id for f in all_files if not is_corpus_eligible(f.path)]

        print(f"[CorpusCleanup] Total files in DB : {total}")
        print(f"[CorpusCleanup] Ineligible files  : {len(bad_file_ids)}")

        if not bad_file_ids:
            print("[CorpusCleanup] ✅ No contaminated rows found — corpus is clean.")
            return

        # Show sample of what would be deleted
        sample_paths = [
            f.path for f in all_files if f.id in set(bad_file_ids)
        ][:20]
        print("\n[CorpusCleanup] Sample ineligible paths:")
        for p in sample_paths:
            print(f"  ✗ {p}")
        if len(bad_file_ids) > 20:
            print(f"  ... and {len(bad_file_ids) - 20} more")

        if dry_run:
            print("\n[CorpusCleanup] DRY RUN — no changes made.")
            return

        print("\n[CorpusCleanup] Deleting contaminated rows...")

        # Delete in dependency order to respect FK constraints:
        # Embeddings → SymbolRelationships → Symbols → Files

        # 1. Delete embeddings linked to ineligible files
        emb_del = session.query(Embedding).filter(
            Embedding.file_id.in_(bad_file_ids)
        ).delete(synchronize_session=False)
        print(f"  Deleted {emb_del} embedding rows")

        # 2. Delete symbol relationships (source or target in bad symbols)
        bad_sym_ids_q = session.query(Symbol.id).filter(
            Symbol.file_id.in_(bad_file_ids)
        )
        bad_sym_ids = [r[0] for r in bad_sym_ids_q.all()]

        if bad_sym_ids:
            rel_del = session.query(SymbolRelationship).filter(
                (SymbolRelationship.source_symbol_id.in_(bad_sym_ids)) |
                (SymbolRelationship.target_symbol_id.in_(bad_sym_ids))
            ).delete(synchronize_session=False)
            print(f"  Deleted {rel_del} symbol_relationship rows")

        # 3. Delete symbols linked to ineligible files
        sym_del = session.query(Symbol).filter(
            Symbol.file_id.in_(bad_file_ids)
        ).delete(synchronize_session=False)
        print(f"  Deleted {sym_del} symbol rows")

        # 4. Delete the file rows themselves
        file_del = session.query(File).filter(
            File.id.in_(bad_file_ids)
        ).delete(synchronize_session=False)
        print(f"  Deleted {file_del} file rows")

        session.commit()
        print(f"\n[CorpusCleanup] ✅ Cleanup complete — {len(bad_file_ids)} ineligible files evicted.")
        print("[CorpusCleanup] Restart the agent to reload a clean in-memory index.")

    except Exception as e:
        session.rollback()
        print(f"[CorpusCleanup] ❌ Error during cleanup: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evict contaminated rows from the Local Cursor index DB."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making any changes.",
    )
    args = parser.parse_args()
    run_cleanup(dry_run=args.dry_run)
