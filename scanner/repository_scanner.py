from pathlib import Path

from repository_intelligence.indexer.file_discovery import (
    discover_files
)

from repository_intelligence.indexer.hash_utils import (
    file_hash
)

from repository_intelligence.indexer.language_detector import (
    detect_language
)


class RepositoryScanner:

    def scan(
        self,
        repository_root: str
    ):

        repository_root = Path(
            repository_root
        ).resolve()

        for file_path in discover_files(
            str(repository_root)
        ):

            yield {
                "path": str(
                    file_path.relative_to(
                        repository_root
                    )
                ),

                "language": detect_language(
                    str(file_path)
                ),

                "file_hash": file_hash(
                    str(file_path)
                ),

                "size_bytes": (
                    file_path.stat().st_size
                )
            }
