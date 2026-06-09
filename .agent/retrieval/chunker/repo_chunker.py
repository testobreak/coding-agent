# retrieval/chunker/repo_chunker.py

from collections import Counter
from pathlib import Path

from retrieval.chunker.chunk_utils import (
    IGNORE_DIRS,
    SUPPORTED_EXTENSIONS,
    MAX_FILE_SIZE_MB
)

from retrieval.chunker.python_chunker import (
    PythonChunker
)

from retrieval.chunker.generic_chunker import (
    GenericChunker
)


class RepoChunker:

    def __init__(self):

        self.python_chunker = (
            PythonChunker()
        )

        self.generic_chunker = (
            GenericChunker()
        )

    # =====================================================
    # FILTERS
    # =====================================================

    def should_skip(
        self,
        path
    ):

        if any(
            part in IGNORE_DIRS
            for part in path.parts
        ):

            return True

        try:

            size_mb = (
                path.stat().st_size
                / (1024 * 1024)
            )

            return size_mb > MAX_FILE_SIZE_MB

        except Exception:

            return True

    # =====================================================
    # BUILD
    # =====================================================

    def build_chunks(
        self,
        root="."
    ):

        root = Path(root)

        all_chunks = []
        files_by_ext = Counter()

        print(
            f"[Chunker] Scanning repository: {root.resolve()}"
        )

        # Walk all files under the root directory
        for path in root.rglob("*"):

            if not path.is_file():
                continue

            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                continue

            if self.should_skip(path):
                continue

            try:

                if suffix == ".py":
                    chunks = (
                        self.python_chunker
                        .chunk_file(path)
                    )
                else:
                    chunks = (
                        self.generic_chunker
                        .chunk_file(path)
                    )

                if chunks:
                    all_chunks.extend(chunks)
                    files_by_ext[suffix] += 1

            except Exception as e:

                print(
                    f"[Chunker Error] "
                    f"{path}: {e}"
                )

        print("\n[Chunker] Scan Summary by Extension:")
        for ext, count in sorted(files_by_ext.items()):
            print(f"  {ext}: {count} files")

        print(
            f"[Chunker] Total chunks generated: {len(all_chunks)}\n"
        )

        return all_chunks

