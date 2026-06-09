# execution/test_runner.py
#
# Runs backend (Maven) and frontend (Vite/npm) tests.
# Pipes raw output through the structured failure parsers so callers
# receive both the raw stdout AND a list of TestFailure objects
# with likely_source_files pre-resolved to actual repo paths.
#

import subprocess
from pathlib import Path

from execution.failure_parser import (
    MavenFailureParser,
    TypeScriptFailureParser,
)


class TestRunner:

    def __init__(self, root="."):
        self.root = Path(root)
        self.maven_parser = MavenFailureParser()
        self.ts_parser = TypeScriptFailureParser()

    # =====================================================
    # BACKEND TESTS (Maven / Spring Boot)
    # =====================================================

    def run_backend_tests(self, test_filter=None):
        """
        Locate pom.xml (checking root and backend/ sub-directory),
        run `mvn test -q`, parse structured failures.
        """
        backend_root = self._find_project_root("pom.xml")

        if backend_root is None:
            # Fallback: original behaviour (pytest)
            return self._run_command(["pytest"], self.root)

        cmd = ["mvn", "test", "-q", "--no-transfer-progress"]
        if test_filter:
            cmd.append(f"-Dtest={test_filter}")
            print(f"[TestRunner] Targeted test run: {test_filter}")
        result = self._run_command(cmd, backend_root)

        # Parse Maven surefire output into structured failures
        stdout = result.get("stdout", "") + result.get("stderr", "")
        failures = self.maven_parser.parse(stdout, repo_root=str(self.root.parent))

        result["failures"] = [
            {
                "test_class": f.test_class,
                "test_method": f.test_method,
                "error_type": f.error_type,
                "message": f.message,
                "stack_frames": f.stack_frames,
                "likely_source_files": f.likely_source_files,
            }
            for f in failures
        ]

        # Ensure success reflects actual test outcome
        if failures:
            result["success"] = False

        return result

    # =====================================================
    # FRONTEND BUILD (Vite / TypeScript)
    # =====================================================

    def run_frontend_build(self):
        """
        Locate package.json (checking root and frontend/ sub-directory),
        run `npm run build`, parse TypeScript errors.
        """
        frontend_root = self._find_project_root("package.json")

        if frontend_root is None:
            return {
                "success": False,
                "error": "package.json not found",
                "failures": [],
            }

        result = self._run_command(
            ["npm", "run", "build"],
            frontend_root,
        )

        stdout = result.get("stdout", "") + result.get("stderr", "")
        failures = self.ts_parser.parse(stdout, repo_root=str(self.root.parent))

        result["failures"] = [
            {
                "error_type": f.error_type,
                "message": f.message,
                "stack_frames": f.stack_frames,
                "likely_source_files": f.likely_source_files,
            }
            for f in failures
        ]

        if failures:
            result["success"] = False

        return result

    # =====================================================
    # FRONTEND TESTS
    # =====================================================

    def run_frontend_tests(self):
        frontend_root = self._find_project_root("package.json")

        if frontend_root is None:
            return {
                "success": False,
                "error": "package.json not found",
                "failures": [],
            }

        result = self._run_command(
            ["npm", "test", "--", "--run"],
            frontend_root,
        )

        stdout = result.get("stdout", "") + result.get("stderr", "")
        failures = self.ts_parser.parse(stdout, repo_root=str(self.root.parent))

        result["failures"] = [
            {
                "error_type": f.error_type,
                "message": f.message,
                "stack_frames": f.stack_frames,
                "likely_source_files": f.likely_source_files,
            }
            for f in failures
        ]

        return result

    # =====================================================
    # PROJECT ROOT DETECTION
    # =====================================================

    def _find_project_root(self, marker_file: str) -> "Path | None":
        """
        Look for `marker_file` in self.root and immediate sub-directories.
        Returns the directory that contains it, or None.
        """
        # Check root itself
        if (self.root / marker_file).exists():
            return self.root

        # Check one level of sub-directories (backend/, frontend/, etc.)
        try:
            for child in self.root.iterdir():
                if child.is_dir() and (child / marker_file).exists():
                    return child
        except Exception:
            pass

        return None

    # =====================================================
    # COMMAND RUNNER
    # =====================================================

    def _run_command(
        self,
        command,
        cwd: Path,
        timeout: int = 600,
    ) -> dict:
        try:
            cmd = list(command)
            import os
            if os.name == "nt":
                if cmd[0] in {"mvn", "npm", "npx"}:
                    cmd[0] = f"{cmd[0]}.cmd"

            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )

            return {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "failures": [],
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Command timeout",
                "failures": [],
            }

        except FileNotFoundError:
            # Safe fallback if cmd[0] is not found
            # e.g. if pytest or mvn is not on the PATH
            if command and command[0] == "pytest":
                try:
                    import sys
                    fallback_cmd = [sys.executable, "-m", "pytest"] + command[1:]
                    result = subprocess.run(
                        fallback_cmd,
                        cwd=cwd,
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout,
                    )
                    return {
                        "success": result.returncode == 0,
                        "return_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "failures": [],
                    }
                except Exception:
                    pass
            return {
                "success": False,
                "error": f"Command not found: {command[0]}",
                "failures": [],
            }
