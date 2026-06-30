# repository/file_manager.py

from pathlib import Path
import shutil


class FileManager:

    IGNORE_DIRS = {
        ".git",
        "__pycache__",
        "node_modules",
        ".agent",
        "tmp"
    }

    def __init__(
        self,
        root="."
    ):

        self.root = Path(
            root
        ).resolve()

    # =====================================================
    # PATH RESOLUTION
    # =====================================================

    def resolve_path(
        self,
        path
    ):

        target = (
            self.root / path
        ).resolve()

        #
        # CRITICAL SECURITY FIX
        #
        # Prevent escaping repository root:
        #
        # ../../secret.txt
        #
        try:

            target.relative_to(
                self.root
            )

        except ValueError:

            raise ValueError(
                "Path outside repository"
            )

        for part in target.parts:

            if part in self.IGNORE_DIRS:

                raise ValueError(
                    f"Ignored path: {path}"
                )

        return target

    # =====================================================
    # READ
    # =====================================================

    def read_file(
        self,
        path,
        start=None,
        end=None
    ):

        target = self.resolve_path(
            path
        )

        # Try reading from VirtualWorkspace overlay filesystem
        content = None
        try:
            from ide.virtual_workspace import VirtualWorkspace
            workspace = VirtualWorkspace.get_instance()
            abs_str = str(target.resolve())
            if workspace.exists(abs_str):
                content = workspace.read_file(abs_str)
        except Exception:
            pass

        if content is None:
            if not target.exists():
                raise FileNotFoundError(
                    path
                )

            content = target.read_text(
                encoding="utf-8",
                errors="ignore"
            )

        lines = content.splitlines()

        if (
            start is not None
            and end is not None
        ):

            sliced = lines[
                start:end
            ]

            return "\n".join(
                sliced
            )

        return content

    # =====================================================
    # WRITE
    # =====================================================

    def write_file(
        self,
        path,
        content,
        backup=True
    ):

        target = self.resolve_path(
            path
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if (
            backup
            and target.exists()
        ):

            backup_path = (
                target.with_suffix(
                    target.suffix
                    + ".bak"
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

    # =====================================================
    # TEMP WRITE
    # =====================================================

    def temp_write(
        self,
        path,
        content
    ):

        temp_dir = (
            self.root
            / ".agent"
            / "tmp"
        )

        temp_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        temp_path = (
            temp_dir / path
        ).resolve()

        #
        # SECURITY FIX
        # Prevent escaping temp folder
        #
        try:

            temp_path.relative_to(
                temp_dir.resolve()
            )

        except ValueError:

            raise ValueError(
                "Path outside temp directory"
            )

        temp_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        temp_path.write_text(
            content,
            encoding="utf-8"
        )

    # =====================================================
    # LIST FILES
    # =====================================================

    def list_files(
        self,
        root="."
    ):

        base = self.resolve_path(
            root
        )

        files = []

        for file in base.rglob("*"):

            if not file.is_file():
                continue

            if any(
                ignored in file.parts
                for ignored in self.IGNORE_DIRS
            ):
                continue

            files.append(

                str(
                    file.relative_to(
                        self.root
                    )
                )
            )

        return files

    # =====================================================
    # SEARCH
    # =====================================================

    def search_code(
        self,
        keyword
    ):

        matches = []

        keyword = str(
            keyword
        ).lower()

        for file in self.list_files():

            try:

                content = self.read_file(
                    file
                )

                if keyword in content.lower():

                    matches.append(
                        file
                    )

            except Exception:

                pass

        return matches
