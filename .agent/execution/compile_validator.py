# execution/compile_validator.py
#
# Language-aware compile validation.
# Runs AFTER validate_file_syntax succeeds, BEFORE committing any modification.
#
# Validation pipeline per modification:
#   1. validate_file_syntax  (brace balance / AST)  ← existing
#   2. validate_compile      (this file)             ← NEW
#   3. diff / tests
#
# Supported:
#   Python  →  python -m py_compile <file>
#   Java    →  mvn -q -DskipTests compile  (from backend root)
#   TS/TSX  →  npx tsc --noEmit            (from frontend root)
#   JS/JSX  →  node --check <file>         (syntax only, no type check)
#

import subprocess
from pathlib import Path
from typing import Optional


class CompileValidator:
    """
    Runs language-specific compile checks on a single modified file.
    Raises RuntimeError with a human-readable message on failure.
    The caller (executor.py) catches this and rolls back the file.
    """

    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root)

    # =========================================================
    # MAIN ENTRY
    # =========================================================

    def validate(self, file_path: str) -> None:
        """
        Run compile check for the given file.
        Raises RuntimeError if compile fails, returns None on success.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".py":
            self._compile_python(path)

        elif suffix == ".java":
            self._compile_java(path)

        elif suffix in {".ts", ".tsx"}:
            self._compile_typescript(path)

        elif suffix in {".js", ".jsx"}:
            self._compile_javascript(path)

        # Other file types (JSON, YAML, CSS…) — no compile step needed

    # =========================================================
    # PYTHON
    # =========================================================

    def _compile_python(self, path: Path) -> None:
        result = subprocess.run(
            ["python", "-m", "py_compile", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"[CompileValidator] Python compile failed for {path.name}:\n"
                f"{result.stderr.strip()}"
            )
        print(f"[CompileValidator] ✓ Python compile OK: {path.name}")

    # =========================================================
    # JAVA (Maven)
    # =========================================================

    def _compile_java(self, path: Path) -> None:
        backend_root = self._find_project_root("pom.xml")
        if backend_root is None:
            print(
                f"[CompileValidator] No pom.xml found — "
                f"skipping Java compile check for {path.name}"
            )
            return

        result = subprocess.run(
            ["mvn", "-q", "-DskipTests", "compile", "--no-transfer-progress"],
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            # Extract the most relevant error lines from Maven output
            error_lines = self._extract_maven_errors(
                result.stdout + result.stderr
            )
            raise RuntimeError(
                f"[CompileValidator] Java compile failed after modifying {path.name}:\n"
                f"{error_lines}"
            )
        print(f"[CompileValidator] ✓ Java compile OK: {path.name}")

    # =========================================================
    # TYPESCRIPT
    # =========================================================

    def _compile_typescript(self, path: Path) -> None:
        frontend_root = self._find_project_root("tsconfig.json")
        if frontend_root is None:
            frontend_root = self._find_project_root("package.json")
        if frontend_root is None:
            print(
                f"[CompileValidator] No tsconfig.json found — "
                f"skipping TypeScript compile check for {path.name}"
            )
            return

        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--pretty", "false"],
            cwd=frontend_root,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            # Filter output to lines mentioning this specific file
            relevant = self._filter_ts_errors(
                result.stdout + result.stderr,
                path.name,
            )
            raise RuntimeError(
                f"[CompileValidator] TypeScript compile failed after modifying {path.name}:\n"
                f"{relevant}"
            )
        print(f"[CompileValidator] ✓ TypeScript compile OK: {path.name}")

    # =========================================================
    # JAVASCRIPT (syntax only via --check)
    # =========================================================

    def _compile_javascript(self, path: Path) -> None:
        result = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"[CompileValidator] JavaScript syntax check failed for {path.name}:\n"
                f"{result.stderr.strip()}"
            )
        print(f"[CompileValidator] ✓ JavaScript syntax OK: {path.name}")

    # =========================================================
    # PROJECT ROOT DETECTION
    # =========================================================

    def _find_project_root(self, marker: str) -> Optional[Path]:
        """Search repo_root and one level of sub-directories for marker file."""
        if (self.repo_root / marker).exists():
            return self.repo_root
        for child in self.repo_root.iterdir():
            if child.is_dir() and (child / marker).exists():
                return child
        return None

    # =========================================================
    # OUTPUT FILTERS
    # =========================================================

    def _extract_maven_errors(self, output: str) -> str:
        """Return only ERROR lines from Maven output (max 20 lines)."""
        lines = [
            line for line in output.splitlines()
            if "[ERROR]" in line or "error:" in line.lower()
        ]
        return "\n".join(lines[:20]) or output[:1000]

    def _filter_ts_errors(self, output: str, filename: str) -> str:
        """Return only lines mentioning the modified file (or first 20 error lines)."""
        lines = output.splitlines()
        relevant = [l for l in lines if filename in l or "error TS" in l]
        return "\n".join(relevant[:20]) or "\n".join(lines[:20])
