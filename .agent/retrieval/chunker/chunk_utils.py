# retrieval/chunker/chunk_utils.py

IGNORE_DIRS = {

    ".git",

    "__pycache__",

    "node_modules",

    "venv",

    ".venv",

    "dist",

    "build",

    "target",

    ".pytest_cache",

    ".mypy_cache",

    ".cache",

    ".agent"
}

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".env",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".md"
}

MAX_FILE_SIZE_MB = 2

