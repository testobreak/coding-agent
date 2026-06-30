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
        self.root = Path(root).resolve()
        self.maven_parser = MavenFailureParser()
        self.ts_parser = TypeScriptFailureParser()

    # =====================================================
    # BACKEND TESTS (Maven / Spring Boot)
    # =====================================================

    def run_backend_tests(self, test_filter=None, touched_files=None):
        """
        Determine subprojects based on touched files, run appropriate test command,
        and validate that tests actually executed (detecting fake zero-test runs).
        """
        from execution.context_engine import ExecutionContextEngine, WorkspaceRoutingError
        from repository_intelligence.workspace import WorkspaceType
        from execution.validation_router import ValidationRouter

        engine = ExecutionContextEngine(self.root)
        
        # Resolve workspaces from touched files
        workspaces = []
        if touched_files:
            for f in touched_files:
                try:
                    ws = engine.resolve_workspace(f)
                    if ws not in workspaces:
                        workspaces.append(ws)
                except WorkspaceRoutingError:
                    pass

        # Fallback to all detected workspaces if none matched
        if not workspaces:
            workspaces = engine.workspaces

        # Default fallback to Python/pytest if no workspaces detected at all
        if not workspaces:
            workspaces = []

        last_result = None
        for ws in workspaces:
            try:
                cmd = list(engine.tool_router.build_command(ws, "test"))
            except KeyError:
                continue

            if test_filter and ws.type in (WorkspaceType.JAVA_MAVEN, WorkspaceType.JAVA_GRADLE):
                cmd.append(f"-Dtest={test_filter}")
                print(f"[TestRunner] Targeted test run: {test_filter}")

            result = self._run_command(cmd, ws.root)
            last_result = result

            output = result.get("stdout", "") + result.get("stderr", "")
            is_valid, reason = ValidationRouter.parse_fake_validation(output, ws.type)

            if not is_valid:
                print(f"[TestRunner] Warning: {reason}")
                result["success"] = False
                result["error"] = reason
                result["failures"] = [{
                    "test_class": "OrchestrationGuard",
                    "test_method": "TestExecution",
                    "error_type": "ZERO_TESTS",
                    "message": reason,
                    "stack_frames": [],
                    "likely_source_files": []
                }]
                return result

            if ws.type in (WorkspaceType.JAVA_MAVEN, WorkspaceType.JAVA_GRADLE):
                failures = self.maven_parser.parse(output, repo_root=str(self.root.parent))
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
                if failures:
                    result["success"] = False

        return last_result or {
            "success": False,
            "error": "No projects resolved to validate",
            "failures": []
        }

    # =====================================================
    # FRONTEND BUILD (Vite / TypeScript)
    # =====================================================

    def run_frontend_build(self):
        """
        Locate package.json and run the build command inside its resolved workspace.
        """
        from execution.context_engine import ExecutionContextEngine
        from repository_intelligence.workspace import WorkspaceType
        engine = ExecutionContextEngine(self.root)
        
        node_ws = next((w for w in engine.workspaces if w.type == WorkspaceType.NODE), None)
        if not node_ws:
            return {
                "success": False,
                "error": "Node workspace not found",
                "failures": [],
            }

        cmd = engine.tool_router.build_command(node_ws, "build")
        result = self._run_command(cmd, node_ws.root)

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
        from execution.context_engine import ExecutionContextEngine
        from repository_intelligence.workspace import WorkspaceType
        engine = ExecutionContextEngine(self.root)
        
        node_ws = next((w for w in engine.workspaces if w.type == WorkspaceType.NODE), None)
        if not node_ws:
            return {
                "success": False,
                "error": "Node workspace not found",
                "failures": [],
            }

        cmd = engine.tool_router.build_command(node_ws, "test")
        result = self._run_command(cmd, node_ws.root)

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
            # Safe fallback if cmd[0] is not found (e.g. pytest or mvn not on path)
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
