from pathlib import Path

LANGUAGE_MAP = {
    ".py": "python",
    ".java": "java",

    ".js": "javascript",
    ".jsx": "javascript",

    ".ts": "typescript",
    ".tsx": "typescript",

    ".go": "go",
    ".cs": "csharp",

    ".cpp": "cpp",
    ".c": "c",

    ".rs": "rust",
    ".php": "php",

    ".html": "html",
    ".css": "css",
    ".scss": "scss",

    ".sql": "sql"
}


def detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return LANGUAGE_MAP.get(ext, "unknown")