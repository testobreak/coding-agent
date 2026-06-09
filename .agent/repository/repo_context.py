# repository/repo_context.py
from pathlib import Path


class RepoContext:

    IMPORTANT_FILES = [
        "pom.xml",
        "package.json",
        "README.md"
    ]

    IGNORE_DIRS = {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build"
    }

    IGNORE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".exe",
        ".lock"
    }

    def __init__(self, root="."):

        self.root = Path(root)

    def summarize(self, files):

        important = []

        for file in files:

            # Ignore unwanted folders
            if any(ignore in file for ignore in self.IGNORE_DIRS):
                continue

            # Ignore unwanted file types
            if any(file.endswith(ext) for ext in self.IGNORE_EXTENSIONS):
                continue

            important.append(file)

        important.sort()

        return "\n".join(important[:200])

    def build_summary(self):

        summary = []

        for file in self.IMPORTANT_FILES:

            path = self.root / file

            if path.exists():

                content = path.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                summary.append(
                    f"\nFILE: {file}\n"
                )

                summary.append(
                    content[:3000]
                )

        return "\n".join(summary)
