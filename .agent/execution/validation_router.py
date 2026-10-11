# execution/validation_router.py
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from execution.project_classifier import ProjectType, ProjectUnit, ProjectClassifier

BACKEND_PROJECT_TYPES: Set[ProjectType] = {
    ProjectType.JAVA_MAVEN,
    ProjectType.JAVA_GRADLE,
    ProjectType.PYTHON,
}
FRONTEND_PROJECT_TYPES: Set[ProjectType] = {ProjectType.NODE}

class ValidationFailureType(Enum):
    WRONG_RUNNER = "wrong_runner"
    ZERO_TESTS = "zero_tests"
    COMPILATION_FAILED = "compilation_failed"
    TEST_FAILED = "test_failed"
    ENVIRONMENT_FAILURE = "environment_failure"

class ValidationRouter:
    def __init__(self, repo_root="."):
        self.repo_root = Path(repo_root)
        self._classifier = ProjectClassifier()

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path.replace("\\", "/").lstrip("./")

    def _detect_units(self) -> List[ProjectUnit]:
        return self._classifier.detect_subprojects(self.repo_root)

    def _match_unit(self, file_path: str, units: List[ProjectUnit]) -> Optional[ProjectUnit]:
        normalized = self._normalize_path(file_path)
        sorted_units = sorted(units, key=lambda u: len(u.root), reverse=True)
        for unit in sorted_units:
            if unit.root and (
                normalized.startswith(unit.root + "/") or normalized == unit.root
            ):
                return unit
        return next((u for u in units if u.root == ""), None)

    def _infer_project_type_from_path(self, file_path: str) -> Optional[ProjectType]:
        normalized = self._normalize_path(file_path).lower()
        parts = normalized.split("/")

        if parts and parts[0] in {"backend", "server", "api"}:
            return ProjectType.JAVA_MAVEN
        if parts and parts[0] in {"frontend", "client", "web", "ui"}:
            return ProjectType.NODE

        if normalized.endswith(".java") or "/src/main/java/" in normalized or normalized.endswith("pom.xml"):
            return ProjectType.JAVA_MAVEN
        if normalized.endswith((".ts", ".tsx", ".jsx", ".js")) or normalized.endswith("package.json"):
            return ProjectType.NODE
        if normalized.endswith(".py") or normalized.endswith(("requirements.txt", "pyproject.toml")):
            return ProjectType.PYTHON
        if normalized.endswith((".gradle", ".gradle.kts")):
            return ProjectType.JAVA_GRADLE

        return None

    def classify_impact(self, touched_files: List[str]) -> Dict[str, Any]:
        """
        Impact-aware validation scope.

        If changed_paths are a subset of backend units, frontend validation is skipped.
        If changed_paths are a subset of frontend units, backend validation is skipped.
        """
        units = self._detect_units()
        normalized_files = [
            self._normalize_path(f) for f in (touched_files or []) if f
        ]

        if not normalized_files:
            return {
                "run_backend": True,
                "run_frontend": False,
                "affected_types": [],
                "reason": "no touched files — skipping frontend (impact unknown)",
            }

        # 1. Filter out irrelevant files (meta, backups, docs, VCS)
        validatable_files = []
        for f in normalized_files:
            parts = f.split("/")
            if any(p in parts for p in (".agent", "agent", ".git", "git", "node_modules", "target", "dist", "build", ".idea", "idea", ".vscode", "vscode", "repository_intelligence")):
                continue
            suffix = Path(f).suffix.lower()
            name = Path(f).name
            if suffix in (".md", ".log", ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".txt") and name not in ("requirements.txt",):
                continue
            if name in (".gitignore", ".gitattributes", "gitignore", "gitattributes", "LICENSE", "README.md"):
                continue
            validatable_files.append(f)

        if not validatable_files:
            return {
                "run_backend": False,
                "run_frontend": False,
                "affected_types": [],
                "reason": "only metadata/documentation files touched — skipping validations",
            }

        affected_types: Set[ProjectType] = set()
        unmatched: List[str] = []
        is_infra_change = False

        for file_path in validatable_files:
            unit = self._match_unit(file_path, units)
            if unit:
                affected_types.add(unit.type)
            else:
                inferred = self._infer_project_type_from_path(file_path)
                if inferred:
                    affected_types.add(inferred)
                else:
                    parts = file_path.lower().split("/")
                    if "infra" in parts or "docker" in file_path.lower() or "compose" in file_path.lower() or "k8s" in parts:
                        is_infra_change = True
                    else:
                        unmatched.append(file_path)

        if not affected_types:
            if is_infra_change and not unmatched:
                return {
                    "run_backend": False,
                    "run_frontend": False,
                    "affected_types": [],
                    "reason": "infra-only change — skipping code validations",
                }
            return {
                "run_backend": True,
                "run_frontend": False,
                "affected_types": [],
                "reason": "touched files did not match any project unit",
            }

        all_backend = affected_types <= BACKEND_PROJECT_TYPES
        all_frontend = affected_types <= FRONTEND_PROJECT_TYPES

        if all_backend:
            return {
                "run_backend": True,
                "run_frontend": False,
                "affected_types": sorted(t.value for t in affected_types),
                "reason": "backend-only change — skipping frontend validation",
            }

        if all_frontend:
            return {
                "run_backend": False,
                "run_frontend": True,
                "affected_types": sorted(t.value for t in affected_types),
                "reason": "frontend-only change — skipping backend validation",
            }

        reason = "cross-stack change — running backend and frontend validation"
        if unmatched:
            reason = (
                "mixed or partially matched paths — running backend and frontend validation"
            )

        return {
            "run_backend": True,
            "run_frontend": True,
            "affected_types": sorted(t.value for t in affected_types),
            "reason": reason,
        }

    def should_run_frontend(self, touched_files: List[str]) -> bool:
        return self.classify_impact(touched_files).get("run_frontend", False)

    def should_run_backend(self, touched_files: List[str]) -> bool:
        return self.classify_impact(touched_files).get("run_backend", True)

    def route_validation(self, touched_files: List[str]) -> List[Dict[str, Any]]:
        """
        Determines the correct command and working directory for validation
        based on the files touched. Supports monorepos with multiple subprojects.
        """
        units = self._detect_units()
        
        # Filter touched files to exclude meta/agent/doc files
        filtered_files = []
        for f in (touched_files or []):
            if not f:
                continue
            norm = self._normalize_path(f)
            parts = norm.split("/")
            if any(p in parts for p in (".agent", ".git", "node_modules", "target", "dist", "build", ".idea", ".vscode", "repository_intelligence")):
                continue
            suffix = Path(norm).suffix.lower()
            name = Path(norm).name
            if suffix in (".md", ".log", ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".txt") and name not in ("requirements.txt",):
                continue
            if name in (".gitignore", ".gitattributes", "LICENSE", "README.md"):
                continue
            filtered_files.append(f)

        if not units:
            return [{"cmd": ["pytest"], "cwd": self.repo_root, "type": ProjectType.PYTHON}]

        # Group touched files by project units
        unit_files = {}
        for f in filtered_files:
            unit = self._match_unit(f, units)
            if unit:
                unit_files.setdefault(unit, []).append(self._normalize_path(f))
            else:
                root_unit = next((u for u in units if u.root == ""), None)
                if root_unit:
                    unit_files.setdefault(root_unit, []).append(self._normalize_path(f))

        # If no touched files, default to all detected units
        if not unit_files:
            for u in units:
                unit_files[u] = []

        routes = []
        for unit, files in unit_files.items():
            cmd = self.get_command(unit.type, files, unit.root)
            routes.append({
                "cmd": cmd,
                "cwd": self.repo_root / unit.root if unit.root else self.repo_root,
                "type": unit.type
            })

        return routes

    def get_command(self, project_type: ProjectType, files: List[str], subproject_root: str) -> List[str]:
        if project_type == ProjectType.JAVA_MAVEN:
            is_multi_file = len(files) > 1
            has_import_changes = False
            has_api_changes = False
            
            if len(files) == 1:
                try:
                    import subprocess
                    import re
                    diff_res = subprocess.run(
                        ["git", "diff", files[0]],
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace"
                    )
                    diff_output = diff_res.stdout
                    
                    if "import " in diff_output:
                        has_import_changes = True
                        
                    public_lines = [
                        line for line in diff_output.splitlines() 
                        if line.startswith("+") and not line.startswith("+++")
                    ]
                    for line in public_lines:
                        if re.search(r'\bpublic\s+(class|interface|enum|record)\b', line):
                            has_api_changes = True
                            break
                        if re.search(r'\bpublic\s+[\w<>]+\s+\w+\s*\(', line):
                            has_api_changes = True
                            break
                except Exception:
                    has_import_changes = True
                    has_api_changes = True
                    
            if not is_multi_file and not has_import_changes and not has_api_changes:
                # Fast module compile check (skipping tests)
                print(f"[ValidationRouter] Bypassing full test suite. Running fast compilation check.")
                if subproject_root:
                    return ["mvn", "-pl", subproject_root, "compile", "-q", "-DskipTests", "--no-transfer-progress"]
                return ["mvn", "compile", "-q", "-DskipTests", "--no-transfer-progress"]
                
            # Slow full compile + unit test run
            if subproject_root:
                return ["mvn", "-pl", subproject_root, "test", "-q", "--no-transfer-progress"]
            return ["mvn", "test", "-q", "--no-transfer-progress"]
        elif project_type == ProjectType.JAVA_GRADLE:
            return ["./gradlew", "test"]
        elif project_type == ProjectType.NODE:
            return ["npm", "test"]
        else:
            return ["pytest"]

    @staticmethod
    def parse_fake_validation(output: str, project_type: ProjectType) -> tuple[bool, str]:
        """
        Parses test output for 'fake validation' (zero tests run) or execution failures.
        Returns (is_valid, reason).
        """
        output_lower = output.lower()
        if project_type == ProjectType.PYTHON:
            if "collected 0 items" in output or "0 passed, 0 failed" in output or "no tests ran" in output_lower:
                return False, "Validation invalid: zero tests executed (wrong runner or missing tests)"
        elif project_type in (ProjectType.JAVA_MAVEN, ProjectType.JAVA_GRADLE):
            if "tests run: 0" in output_lower or "tests run: 0," in output_lower or "no tests found" in output_lower:
                return False, "Validation invalid: zero tests executed in Maven/Gradle"
        elif project_type == ProjectType.NODE:
            if "0 passed" in output_lower and "0 failed" in output_lower:
                return False, "Validation invalid: zero tests executed in Node"

        return True, "Success"
