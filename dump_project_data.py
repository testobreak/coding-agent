from pathlib import Path
from datetime import datetime

# Folders to scan.
# Keeping both because your setup may have either "agent" or ".agent".
FOLDERS_TO_DUMP = [
    "agent",
    ".agent",
    "repository_intelligence"
]

OUTPUT_FILE = "project_dump.txt"

ALLOWED_EXTENSIONS = {
    ".py", ".java", ".js", ".ts", ".jsx", ".tsx",
    ".json", ".xml", ".yml", ".yaml",
    ".md", ".txt", ".properties",
    ".html", ".css", ".sql", ".sh",
    ".feature", ".gradle", ".pom",
    ".toml", ".ini", ".cfg", ".conf",
    ".lock"
}

ALLOWED_FILE_NAMES = {
    "Dockerfile",
    "Makefile",
    "README",
    "requirements",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    ".gitignore",
    ".dockerignore"
}

IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "target",
    "build",
    "dist",
    "venv",
    ".venv",
    "logs",
    ".mypy_cache",
    ".pytest_cache"
}

# Do not dump secrets into LLM context.
SKIP_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.dev",
    ".env.prod",
    ".env.production",
    ".env.staging"
}


def detect_project_root() -> Path:
    """
    Detect project root by walking upward from current directory.
    Looks for repository_intelligence and either agent/.agent.
    """
    current = Path.cwd().resolve()

    for path in [current, *current.parents]:
        has_repo_intel = (path / "repository_intelligence").exists()
        has_agent = (path / "agent").exists() or (path / ".agent").exists()

        if has_repo_intel and has_agent:
            return path

    return current


def should_skip_file(file_path: Path) -> bool:
    if any(part in IGNORE_DIRS for part in file_path.parts):
        return True

    if file_path.name in SKIP_FILE_NAMES:
        return True

    if file_path.name in ALLOWED_FILE_NAMES:
        return False

    if file_path.suffix.lower() in ALLOWED_EXTENSIONS:
        return False

    return True


def read_file_content(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return file_path.read_text(encoding="latin-1")
        except Exception as exc:
            return f"[Could not read file using latin-1: {exc}]"
    except Exception as exc:
        return f"[Could not read file: {exc}]"


def dump_folder_data(base_path: Path, output_file) -> int:
    dumped_count = 0

    for file_path in sorted(base_path.rglob("*")):
        if file_path.is_dir():
            continue

        if should_skip_file(file_path):
            continue

        content = read_file_content(file_path)

        output_file.write("\n" + "=" * 120 + "\n")
        output_file.write(f"FILE: {file_path}\n")
        output_file.write("=" * 120 + "\n\n")
        output_file.write(content)
        output_file.write("\n\n")

        dumped_count += 1
        print(f"Dumped: {file_path}")

    return dumped_count


def main():
    root_dir = detect_project_root()
    output_path = root_dir / OUTPUT_FILE

    total_files_dumped = 0
    scanned_folders = set()

    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write("PROJECT DATA DUMP\n")
        output_file.write(f"Generated At: {datetime.now()}\n")
        output_file.write(f"Root Directory: {root_dir}\n")
        output_file.write("=" * 120 + "\n\n")

        for folder_name in FOLDERS_TO_DUMP:
            folder_path = root_dir / folder_name

            if folder_path in scanned_folders:
                continue

            scanned_folders.add(folder_path)

            if not folder_path.exists():
                output_file.write(f"\n[Folder not found]: {folder_path}\n")
                print(f"Folder not found: {folder_path}")
                continue

            if not folder_path.is_dir():
                output_file.write(f"\n[Not a folder]: {folder_path}\n")
                print(f"Not a folder: {folder_path}")
                continue

            output_file.write(f"\n\n{'#' * 120}\n")
            output_file.write(f"FOLDER: {folder_path}\n")
            output_file.write(f"{'#' * 120}\n\n")

            print(f"\nScanning folder: {folder_path}")
            dumped_count = dump_folder_data(folder_path, output_file)
            total_files_dumped += dumped_count

    print("\nDone.")
    print(f"Project root: {root_dir}")
    print(f"Output file: {output_path}")
    print(f"Total files dumped: {total_files_dumped}")


if __name__ == "__main__":
    main()