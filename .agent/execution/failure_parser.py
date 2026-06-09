# execution/failure_parser.py
#
# Parses raw test-runner stdout into structured TestFailure objects.
# Two parsers: MavenFailureParser (Java / Spring Boot) and
# TypeScriptFailureParser (Vite / tsc build errors).
#

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class TestFailure:
    """
    One structured test failure extracted from raw runner output.
    `likely_source_files` is the list of repo-relative paths inferred
    from the stack trace — these are fed directly into RepairEngine as
    concrete modification targets.
    """
    test_class: str = ""
    test_method: str = ""
    error_type: str = ""
    message: str = ""
    stack_frames: List[str] = field(default_factory=list)
    likely_source_files: List[str] = field(default_factory=list)


# =========================================================
# MAVEN / SUREFIRE FAILURE PARSER
# =========================================================

class MavenFailureParser:
    """
    Parses `mvn test` / `mvn surefire` output and extracts structured
    TestFailure objects including stack-trace-derived source file paths.
    """

    # Matches:  "Tests run: 3, Failures: 1, Errors: 0"
    _SUMMARY_RE = re.compile(
        r"Tests run:\s*(\d+).*?Failures:\s*(\d+).*?Errors:\s*(\d+)",
        re.IGNORECASE,
    )

    # Matches test class header line in surefire output:
    # "Running com.acme.hrms.employee.service.EmployeeServiceTest"
    _TEST_CLASS_RE = re.compile(r"Running\s+([\w.]+)")

    # Matches individual failure block header:
    # "--- FAILURE: testGetEmployee(com.acme.hrms.employee.service.EmployeeServiceTest)"
    _FAILURE_HEADER_RE = re.compile(
        r"(?:FAILURE|ERROR)[:\s]+([\w<>]+)\(([\w.]+)\)"
    )

    # Matches exception type on its own line, e.g. "java.lang.NullPointerException: ..."
    _EXCEPTION_RE = re.compile(r"^\s*([\w.]+Exception|[\w.]+Error):\s*(.*)")

    # Matches stack frame like "at com.acme.hrms.employee.service.EmployeeService.getById(EmployeeService.java:42)"
    _STACK_FRAME_RE = re.compile(
        r"at\s+([\w.$]+)\.([\w$<>]+)\(([\w]+\.java):(\d+)\)"
    )

    def parse(self, stdout: str, repo_root: str = "..") -> List[TestFailure]:
        failures: List[TestFailure] = []
        current: Optional[TestFailure] = None
        root = Path(repo_root)

        for line in stdout.splitlines():
            # Detect new test class
            m = self._TEST_CLASS_RE.search(line)
            if m:
                current = TestFailure(test_class=m.group(1))
                continue

            # Detect failure/error header
            m = self._FAILURE_HEADER_RE.search(line)
            if m:
                method_name = m.group(1)
                class_name = m.group(2)
                if current is None:
                    current = TestFailure(test_class=class_name)
                current.test_method = method_name
                current.test_class = class_name
                continue

            # Exception type and message
            m = self._EXCEPTION_RE.match(line)
            if m and current is not None:
                if not current.error_type:
                    current.error_type = m.group(1)
                    current.message = m.group(2).strip()
                continue

            # Stack frames
            m = self._STACK_FRAME_RE.search(line)
            if m and current is not None:
                frame_str = f"{m.group(3)}:{m.group(4)}"
                current.stack_frames.append(frame_str)

                # Try to resolve to an actual repo file path
                java_filename = m.group(3)  # e.g. "EmployeeService.java"
                resolved = self._find_java_file(root, java_filename)
                if resolved and resolved not in current.likely_source_files:
                    current.likely_source_files.append(resolved)
                continue

            # Blank line after a failure block — flush current
            if line.strip() == "" and current is not None:
                if current.error_type or current.stack_frames:
                    failures.append(current)
                    current = TestFailure(test_class=current.test_class)

        # Flush last open failure
        if current is not None and (current.error_type or current.stack_frames):
            failures.append(current)

        return failures

    def _find_java_file(self, root: Path, filename: str) -> Optional[str]:
        """Walk the repo looking for a Java file by basename."""
        try:
            for match in root.rglob(filename):
                if match.is_file():
                    return str(match)
        except Exception:
            pass
        return None

    def has_failures(self, stdout: str) -> bool:
        m = self._SUMMARY_RE.search(stdout)
        if m:
            failures = int(m.group(2))
            errors = int(m.group(3))
            return (failures + errors) > 0
        return "BUILD FAILURE" in stdout or "TESTS FAILED" in stdout.upper()


# =========================================================
# TYPESCRIPT / VITE FAILURE PARSER
# =========================================================

class TypeScriptFailureParser:
    """
    Parses `tsc --noEmit` or `vite build` output and extracts structured
    TestFailure objects with file paths and line numbers.

    Handles both tsc and vite error formats:
      src/features/employee/EmployeeForm.tsx(42,17): error TS2322: ...
      [vite:esbuild] Transform failed with 1 error(s):
      src/features/employee/EmployeeForm.tsx:42:17: ERROR: ...
    """

    # tsc format: "path/to/File.tsx(line,col): error TSxxxx: message"
    _TSC_ERROR_RE = re.compile(
        r"^([\w/\\.\-]+\.tsx?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.*)"
    )

    # vite/esbuild format: "path/to/File.tsx:line:col: ERROR: message"
    _VITE_ERROR_RE = re.compile(
        r"^([\w/\\.\-]+\.tsx?):(\d+):(\d+):\s+ERROR:\s+(.*)"
    )

    def parse(self, stdout: str, repo_root: str = "..") -> List[TestFailure]:
        failures: List[TestFailure] = []
        root = Path(repo_root)

        for line in stdout.splitlines():
            line = line.strip()

            # tsc format
            m = self._TSC_ERROR_RE.match(line)
            if m:
                rel_path = m.group(1).replace("\\", "/")
                abs_path = self._resolve(root, rel_path)
                failure = TestFailure(
                    error_type=m.group(4),
                    message=m.group(5).strip(),
                    stack_frames=[f"{rel_path}:{m.group(2)}:{m.group(3)}"],
                    likely_source_files=[abs_path] if abs_path else [rel_path],
                )
                failures.append(failure)
                continue

            # vite/esbuild format
            m = self._VITE_ERROR_RE.match(line)
            if m:
                rel_path = m.group(1).replace("\\", "/")
                abs_path = self._resolve(root, rel_path)
                failure = TestFailure(
                    error_type="BuildError",
                    message=m.group(4).strip(),
                    stack_frames=[f"{rel_path}:{m.group(2)}:{m.group(3)}"],
                    likely_source_files=[abs_path] if abs_path else [rel_path],
                )
                failures.append(failure)
                continue

        return failures

    def _resolve(self, root: Path, rel_path: str) -> Optional[str]:
        candidate = root / rel_path
        if candidate.exists():
            return str(candidate)
        # Try searching from frontend dir
        for match in root.rglob(Path(rel_path).name):
            if match.is_file():
                return str(match)
        return None

    def has_failures(self, stdout: str) -> bool:
        return (
            "error TS" in stdout
            or "ERROR:" in stdout
            or "Build failed" in stdout
        )
