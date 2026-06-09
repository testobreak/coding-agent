# analysis/impact_analyzer.py
#
# Given a modified file, determines:
#   1. Which other files depend on it (dependents)
#   2. Which test classes are affected (by package/name heuristics)
#   3. Which test methods could be affected (for targeted mvn -Dtest=... runs)
#
# Used by:
#   executor.py → run_backend_tests → pass test_filter to TestRunner
#   TestRunner  → mvn -Dtest=X,Y test  (only run affected tests)
#
# This dramatically speeds up validation on large repos by avoiding
# full test suite runs when only one service method changed.
#

import re
from pathlib import Path
from typing import List, Dict, Set, Optional

from analysis.dependency_graph import DependencyGraph


class ImpactAnalyzer:
    """
    Change impact analysis: modified file → affected tests.
    """

    def __init__(self, graph: DependencyGraph = None, repo_root: str = "."):
        self.graph = graph or DependencyGraph()
        self.repo_root = Path(repo_root)

    # =========================================================
    # MAIN
    # =========================================================

    def analyze(self, modified_file: str) -> Dict:
        """
        Returns a dict:
        {
            "modified_file": str,
            "dependent_files": [str, ...],
            "affected_test_classes": [str, ...],    # Java FQCN
            "affected_test_files": [str, ...],      # absolute paths
            "test_filter": "ClassName1+ClassName2", # for mvn -Dtest=
        }
        """
        modified_file = str(modified_file)

        # Files that import the modified file (1-hop callers)
        dependent_files = self.graph.dependents_of(modified_file, depth=1)

        # The modified file itself could be a test — include it
        all_affected = [modified_file] + dependent_files

        # Find test files among affected
        test_files = [f for f in all_affected if self._is_test_file(f)]
        test_classes = [self._file_to_test_class(f) for f in test_files]
        test_classes = [c for c in test_classes if c]

        # Also scan for test files that name-match the modified class
        inferred = self._infer_test_files(modified_file)
        for tf in inferred:
            if tf not in test_files:
                test_files.append(tf)
                tc = self._file_to_test_class(tf)
                if tc and tc not in test_classes:
                    test_classes.append(tc)

        # Maven test filter string
        test_filter = "+".join(test_classes) if test_classes else None

        return {
            "modified_file": modified_file,
            "dependent_files": dependent_files,
            "affected_test_files": test_files,
            "affected_test_classes": test_classes,
            "test_filter": test_filter,
        }

    def affected_test_classes(self, modified_file: str) -> List[str]:
        """Convenience: just return the test class list."""
        return self.analyze(modified_file)["affected_test_classes"]

    def test_filter_string(self, modified_file: str) -> Optional[str]:
        """Convenience: return the mvn -Dtest= filter string or None."""
        return self.analyze(modified_file)["test_filter"]

    # =========================================================
    # HELPERS
    # =========================================================

    def _is_test_file(self, file_path: str) -> bool:
        """Heuristic: test files contain 'Test' in name or live in src/test."""
        path = Path(file_path)
        return (
            "Test" in path.stem
            or "test" in path.parts
            or "tests" in path.parts
            or path.stem.endswith("Spec")
            or path.stem.startswith("test_")
        )

    def _file_to_test_class(self, file_path: str) -> Optional[str]:
        """
        Convert a Java test file path to a FQCN for mvn -Dtest=.
        e.g. .../src/test/java/com/acme/hrms/employee/EmployeeServiceTest.java
             → com.acme.hrms.employee.EmployeeServiceTest
        """
        path = Path(file_path)
        if path.suffix != ".java":
            return path.stem  # TypeScript test: just use file name

        try:
            parts = path.with_suffix("").parts
            # Find 'java' dir index inside src/test/java
            for i, part in enumerate(parts):
                if part == "java" and i > 0:
                    return ".".join(parts[i + 1:])
        except Exception:
            pass
        return path.stem

    def _infer_test_files(self, modified_file: str) -> List[str]:
        """
        Find test files that likely test the modified class by name convention.
        e.g. EmployeeService.java → EmployeeServiceTest.java
        """
        path = Path(modified_file)
        stem = path.stem
        test_name = stem + "Test"
        found = []
        try:
            for match in self.repo_root.rglob(test_name + path.suffix):
                if match.is_file():
                    found.append(str(match))
        except Exception:
            pass
        return found
