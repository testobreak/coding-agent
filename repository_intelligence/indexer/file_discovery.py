from pathlib import Path


IGNORED_DIRS = {
    ".git",
    "__pycache__",

    ".venv",
    "venv",

    "node_modules",

    "dist",
    "build",
    "target",

    ".pytest_cache",
    ".mypy_cache",

    ".cache",
    ".agent"
}


def discover_files(root_path: str):

    root = Path(root_path)

    for path in root.rglob("*"):

        if not path.is_file():
            continue

        if any(
            part in IGNORED_DIRS
            for part in path.parts
        ):
            continue

        yield path