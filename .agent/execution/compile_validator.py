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
from core.validation_mode import ValidationState


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

    def validate(self, file_path: str) -> ValidationState:
        """
        Run compile check for the given file.
        Returns ValidationState.
        """
        from core.validation_mode import ValidationState
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".py":
            return self._compile_python(path)

        elif suffix == ".java":
            return self._compile_java(path)

        elif suffix in {".ts", ".tsx"}:
            return self._compile_typescript(path)

        elif suffix in {".js", ".jsx"}:
            return self._compile_javascript(path)

        return ValidationState.SKIPPED

    # =========================================================
    # PYTHON
    # =========================================================

    def _compile_python(self, path: Path) -> ValidationState:
        from core.validation_mode import ValidationState
        import sys
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return ValidationState.UNAVAILABLE

        if result.returncode != 0:
            return ValidationState.FAILED
        print(f"[CompileValidator] ✓ Python compile OK: {path.name}")
        return ValidationState.PASSED

    # =========================================================
    # JAVA (Maven)
    # =========================================================

    def _compile_java(self, path: Path) -> ValidationState:
        from core.validation_mode import ValidationState
        backend_root = self._find_project_root("pom.xml")
        if backend_root is None:
            print(
                f"[CompileValidator] No pom.xml found — "
                f"skipping Java compile check for {path.name}"
            )
            return ValidationState.SKIPPED

        try:
            result = subprocess.run(
                ["mvn", "-q", "-DskipTests", "compile", "--no-transfer-progress"],
                cwd=backend_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            print(f"[CompileValidator] mvn command not found on PATH — Java compile check unavailable")
            return ValidationState.UNAVAILABLE

        if result.returncode != 0:
            return ValidationState.FAILED
        print(f"[CompileValidator] ✓ Java compile OK: {path.name}")
        return ValidationState.PASSED

    # =========================================================
    # TYPESCRIPT
    # =========================================================

    def _compile_typescript(self, path: Path) -> ValidationState:
        from core.validation_mode import ValidationState
        frontend_root = self._find_project_root("tsconfig.json")
        if frontend_root is None:
            frontend_root = self._find_project_root("package.json")
        if frontend_root is None:
            print(
                f"[CompileValidator] No tsconfig.json found — "
                f"skipping TypeScript compile check for {path.name}"
            )
            return ValidationState.SKIPPED

        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", "--pretty", "false"],
                cwd=frontend_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            print(f"[CompileValidator] npx command not found on PATH — TypeScript compile check unavailable")
            return ValidationState.UNAVAILABLE

        if result.returncode != 0:
            return ValidationState.FAILED
        print(f"[CompileValidator] ✓ TypeScript compile OK: {path.name}")
        return ValidationState.PASSED

    # =========================================================
    # JAVASCRIPT (syntax only via --check)
    # =========================================================

    def _compile_javascript(self, path: Path) -> ValidationState:
        from core.validation_mode import ValidationState
        try:
            result = subprocess.run(
                ["node", "--check", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return ValidationState.UNAVAILABLE

        if result.returncode != 0:
            return ValidationState.FAILED
        print(f"[CompileValidator] ✓ JavaScript syntax OK: {path.name}")
        return ValidationState.PASSED

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
