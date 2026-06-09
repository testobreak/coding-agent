from sqlalchemy import func

from repository_intelligence.models.file import File
from repository_intelligence.models.repository import Repository


class FileIndexer:

    def known_hashes(
        self,
        session,
        repository: Repository
    ) -> dict[str, str]:

        rows = (
            session.query(File.path, File.file_hash)
            .filter(File.repository_id == repository.id)
            .all()
        )

        return {
            path.replace("\\", "/"): file_hash
            for path, file_hash in rows
        }

    def upsert(
        self,
        session,
        repository: Repository,
        file_info: dict,
        mark_indexed: bool = True
    ) -> File:

        file_row = (
            session.query(File)
            .filter(
                File.repository_id == repository.id,
                File.path == file_info["path"]
            )
            .one_or_none()
        )

        if not file_row:
            file_row = File(
                repository_id=repository.id,
                path=file_info["path"],
                language=file_info["language"],
                file_hash="",
                size_bytes=file_info["size_bytes"]
            )
            session.add(file_row)
            session.flush()

        file_row.language = file_info["language"]
        file_row.size_bytes = file_info["size_bytes"]
        file_row.updated_at = func.now()

        if mark_indexed:
            file_row.file_hash = file_info["file_hash"]

        session.flush()

        return file_row

    def sync(
        self,
        session,
        repository: Repository,
        scanned_files: list[dict]
    ) -> dict:

        scanned_paths = {
            file_info["path"]
            for file_info in scanned_files
        }
        known_hashes = self.known_hashes(
            session,
            repository
        )
        known_paths = set(known_hashes)
        inserted = 0
        updated = 0
        unchanged = 0

        for file_info in scanned_files:
            existing_hash = known_hashes.get(file_info["path"])
            file_row = self.upsert(
                session,
                repository,
                file_info,
                mark_indexed=True
            )

            if existing_hash is None:
                inserted += 1
            elif existing_hash != file_row.file_hash:
                updated += 1
            else:
                unchanged += 1

        removed = self.delete_removed(
            session,
            repository,
            list(known_paths - scanned_paths)
        )

        return {
            "scanned_files": len(scanned_files),
            "inserted_files": inserted,
            "updated_files": updated,
            "unchanged_files": unchanged,
            "removed_files": removed
        }

    def delete_removed(
        self,
        session,
        repository: Repository,
        removed_paths: list[str]
    ) -> int:

        if not removed_paths:
            return 0

        removed_files = (
            session.query(File)
            .filter(
                File.repository_id == repository.id,
                File.path.in_(removed_paths)
            )
            .all()
        )

        removed = len(removed_files)

        for file_row in removed_files:
            session.delete(file_row)

        return removed
