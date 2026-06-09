# export_agent_single_file.py

from pathlib import Path


SOURCE_FOLDER = "."

OUTPUT_FILE = "agent_dump.md"


IGNORE_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".cache",
    "logs",
    "tmp"
}

IGNORE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".pkl",
    ".faiss",
    ".bin",
    ".db"
}


EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".java": "java",
    ".json": "json",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown"
}


def should_ignore(path):

    # prevent recursive self-inclusion
    if path.name == OUTPUT_FILE:
        return True

    for part in path.parts:

        if part in IGNORE_DIRS:
            return True

    if path.suffix.lower() in IGNORE_EXTENSIONS:
        return True

    return False


def get_language(path):

    return EXTENSION_LANGUAGE_MAP.get(
        path.suffix.lower(),
        ""
    )


def export_to_single_file():

    source = Path(SOURCE_FOLDER).resolve()

    output = Path(OUTPUT_FILE).resolve()

    if not source.exists():

        print(
            f"Source folder not found: {source}"
        )

        return

    files_written = 0

    with open(output, "w", encoding="utf-8") as out:

        out.write(
            "# AGENT REPOSITORY EXPORT\n\n"
        )

        for file in sorted(source.rglob("*")):

            if file.is_dir():
                continue

            if should_ignore(file):
                continue

            relative_path = file.relative_to(source)

            try:

                content = file.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

            except Exception as e:

                print(
                    f"Skipped: "
                    f"{relative_path} ({e})"
                )

                continue

            language = get_language(file)

            separator = "=" * 100

            out.write(
                f"\n{separator}\n"
            )

            out.write(
                f"PATH: {relative_path}\n"
            )

            out.write(
                f"{separator}\n\n"
            )

            out.write(
                f"```{language}\n"
            )

            out.write(content)

            out.write("\n```\n\n")

            files_written += 1

            print(
                f"Added: {relative_path}"
            )

    print("\n================================")

    print(
        "Export completed"
    )

    print(
        f"Files added: {files_written}"
    )

    print(
        f"Output file: {output}"
    )

    print("================================")


if __name__ == "__main__":

    export_to_single_file()
