from pathlib import Path
import subprocess

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
                "absolute_path": str(file_path),

                "path": str(
                    file_path.relative_to(
                        repository_root
                    )
                ).replace("\\", "/"),

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

    def scan_changes(
        self,
        repository_root: str,
        known_hashes: dict[str, str]
    ):

        repository_root_path = Path(repository_root).resolve()

        if not known_hashes:
            scanned = list(
                self.scan(str(repository_root_path))
            )
            return {
                "scanned": scanned,
                "changed": scanned,
                "unchanged": [],
                "removed": []
            }

        candidate_paths = self._git_changed_paths(
            repository_root_path
        )

        if candidate_paths is None:
            candidate_paths = {
                info["path"]
                for info in self.scan(str(repository_root_path))
            }

        changed = []
        unchanged = []
        scanned = []

        for relative_path in sorted(candidate_paths):
            absolute_path = repository_root_path / relative_path

            if not absolute_path.is_file():
                continue

            info = {
                "absolute_path": str(absolute_path),
                "path": relative_path,
                "language": detect_language(str(absolute_path)),
                "file_hash": file_hash(str(absolute_path)),
                "size_bytes": absolute_path.stat().st_size
            }
            scanned.append(info)

            if known_hashes.get(relative_path) == info["file_hash"]:
                unchanged.append(info)
            else:
                changed.append(info)

        removed = [
            path for path in known_hashes
            if not (repository_root_path / path).is_file()
        ]

        return {
            "scanned": scanned,
            "changed": changed,
            "unchanged": unchanged,
            "removed": removed
        }

    def _git_changed_paths(
        self,
        repository_root: Path
    ) -> set[str] | None:

        try:
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={repository_root.as_posix()}",
                    "status",
                    "--porcelain"
                ],
                cwd=repository_root,
                check=False,
                capture_output=True,
                text=True
            )
        except Exception:
            return None

        if result.returncode != 0:
            return None

        changed = set()

        for line in result.stdout.splitlines():
            if not line.strip():
                continue

            path = line[3:].strip()

            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()

            if path:
                changed.add(path.replace("\\", "/"))

        return changed
