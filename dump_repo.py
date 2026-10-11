#!/usr/bin/env python3
from pathlib import Path
import math
import os

TARGET_FOLDERS = [
    ".agent",
    "repository_intelligence",
    "vscode-extension",
]

OUTPUT_FILES = [
    "repo_dump_part1.txt",
    "repo_dump_part2.txt",
    "repo_dump_part3.txt",
    "repo_dump_part4.txt",
]

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    "out",
    ".idea",
    ".pytest_cache",
}

EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".class",
    ".jar",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".db",
    ".sqlite",
    ".lock",
}

MAX_FILE_SIZE_MB = 5


def should_skip(path: Path):
    if path.suffix.lower() in EXCLUDED_EXTENSIONS:
        return True

    try:
        size_mb = path.stat().st_size / (1024 * 1024)
        return size_mb > MAX_FILE_SIZE_MB
    except OSError:
        return True


def collect_files(root: Path):
    files = []

    for folder in TARGET_FOLDERS:
        folder_path = root / folder

        if not folder_path.exists():
            print(f"[WARN] Missing folder: {folder}")
            continue

        for current_root, dirs, filenames in os.walk(folder_path):
            dirs[:] = [directory for directory in dirs if directory not in EXCLUDED_DIRS]

            for filename in filenames:
                path = Path(current_root) / filename

                if not should_skip(path):
                    files.append(path)

    return sorted(files)


def dump_files(files: list[Path], output_path: Path):
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"REPO DUMP -> {output_path.name}\n")
        out.write(f"FILES IN THIS PART -> {len(files)}\n\n")

        for file_path in files:
            out.write("\n" + "=" * 120 + "\n")
            out.write(f"FILE: {file_path}\n")
            out.write("=" * 120 + "\n\n")

            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    out.write(file.read())
                    out.write("\n")
            except UnicodeDecodeError:
                out.write("[Skipped: Binary / non-UTF8 file]\n")
            except OSError as error:
                out.write(f"[ERROR] Could not read file: {error}\n")


def split_into_parts(files: list[Path], number_of_parts: int):
    if not files:
        return [[] for _ in range(number_of_parts)]

    chunk_size = math.ceil(len(files) / number_of_parts)

    return [
        files[index:index + chunk_size]
        for index in range(0, len(files), chunk_size)
    ]


def main():
    repo_root = Path.cwd()
    files = collect_files(repo_root)

    parts = split_into_parts(files, len(OUTPUT_FILES))

    # Ensures all four output files are created,
    # even when there are fewer files than expected.
    while len(parts) < len(OUTPUT_FILES):
        parts.append([])

    for index, output_file in enumerate(OUTPUT_FILES):
        dump_files(parts[index], repo_root / output_file)

    print(f"\nDumped {len(files)} files into {len(OUTPUT_FILES)} parts.")
    print("Created:")

    for index, output_file in enumerate(OUTPUT_FILES):
        print(f" - {output_file} ({len(parts[index])} files)")


if __name__ == "__main__":
    main()