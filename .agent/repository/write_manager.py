# repository/write_manager.py

from pathlib import Path
import shutil


class WriteManager:

    def __init__(self, root="."):

        self.root = Path(root).resolve()

    def write_file(
        self,
        path: str,
        content: str,
        backup=True
    ):

        target = (
            self.root / path
        ).resolve()

        try:
            target.relative_to(
                self.root
            )

        except ValueError:

            raise RuntimeError(
                f"Illegal path: {path}"
            )

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if backup and target.exists():

            backup_path = (
                target.with_suffix(
                    target.suffix + ".bak"
                )
            )

            shutil.copy2(
                target,
                backup_path
            )

        target.write_text(
            content,
            encoding="utf-8"
        )

        return {
            "success": True,
            "path": path
        }
