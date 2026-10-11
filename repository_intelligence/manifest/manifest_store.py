# repository_intelligence/manifest/manifest_store.py

import os
from datetime import datetime
from typing import Optional

from repository_intelligence.manifest.models import RepositoryManifest, FileRecord
from repository_intelligence.manifest.manifest_builder import (
    ManifestBuilder, detect_language, detect_module, detect_file_type, get_file_hash_and_size, is_generated_source
)

class ManifestStore:
    _manifest: Optional[RepositoryManifest] = None
    _repo_root: Optional[str] = None

    @classmethod
    def get_manifest(cls, repo_root: str) -> RepositoryManifest:
        if cls._manifest is None or cls._repo_root != repo_root:
            print(f"[ManifestStore] Initializing Repository Manifest for {repo_root}...")
            cls._repo_root = repo_root
            cls._manifest = ManifestBuilder.build(repo_root)
        return cls._manifest

    @classmethod
    def clear_cache(cls):
        cls._manifest = None
        cls._repo_root = None

    @classmethod
    def update_file(cls, repo_root: str, rel_path: str):
        """
        Incrementally updates a single file's manifest record when changed on disk,
        avoiding a full project traverse.
        """
        manifest = cls.get_manifest(repo_root)
        abs_path = os.path.join(repo_root, rel_path)

        # 1. If file does not exist, delete it from manifest
        if not os.path.exists(abs_path):
            if rel_path in manifest.files_by_path:
                record = manifest.files_by_path.pop(rel_path)
                # Remove from module index
                if record.module in manifest.files_by_module:
                    manifest.files_by_module[record.module] = [
                        r for r in manifest.files_by_module[record.module] if r.path != rel_path
                    ]
                # Remove from language index
                if record.language in manifest.files_by_language:
                    manifest.files_by_language[record.language] = [
                        r for r in manifest.files_by_language[record.language] if r.path != rel_path
                    ]
            return

        # 2. Skip if it is generated or not a source/valid file
        ext = os.path.splitext(rel_path)[1]
        from repository_intelligence.manifest.manifest_builder import IGNORE_EXTENSIONS
        if ext in IGNORE_EXTENSIONS or is_generated_source(abs_path):
            # If it was in the manifest before, remove it
            cls.update_file(repo_root, rel_path) # Call recursive deletion path
            return

        # 3. Build single FileRecord
        lang = detect_language(rel_path)
        module = detect_module(rel_path)
        file_type = detect_file_type(rel_path, ext.lower())
        h, size = get_file_hash_and_size(abs_path)

        # Count symbols from DB if available
        sym_count = 0
        try:
            from repository_intelligence.db.connection import SessionLocal
            from repository_intelligence.models.symbol import Symbol
            from repository_intelligence.models.file import File
            db = SessionLocal()
            try:
                sym_count = db.query(Symbol).join(File, Symbol.file_id == File.id)\
                              .filter(File.path == rel_path).count()
            except Exception:
                pass
            finally:
                db.close()
        except Exception:
            pass

        record = FileRecord(
            path=rel_path,
            language=lang,
            module=module,
            file_type=file_type,
            symbol_count=sym_count,
            hash=h,
            size_bytes=size,
            indexed_at=datetime.utcnow().isoformat()
        )

        # Evict old record first to update indices cleanly
        if rel_path in manifest.files_by_path:
            old = manifest.files_by_path[rel_path]
            if old.module in manifest.files_by_module:
                manifest.files_by_module[old.module] = [
                    r for r in manifest.files_by_module[old.module] if r.path != rel_path
                ]
            if old.language in manifest.files_by_language:
                manifest.files_by_language[old.language] = [
                    r for r in manifest.files_by_language[old.language] if r.path != rel_path
                ]

        # Insert new record
        manifest.files_by_path[rel_path] = record
        manifest.files_by_module.setdefault(module, []).append(record)
        manifest.files_by_language.setdefault(lang, []).append(record)
