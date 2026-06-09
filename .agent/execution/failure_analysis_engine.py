# execution/failure_analysis_engine.py
#
# Converts structured TestFailure objects (from failure_parser.py) into
# concrete REPAIR actions with targets=likely_source_files.
#
# This is the missing link between:
#   TestRunner → FailureParser → FailureAnalysisEngine → REPAIR(targets)
#
# It also writes `state.test_failure_targets` so RepairEngine and
# repair_from_context can use deterministic targets instead of guessing.
#

from typing import List, Dict, Any

from planning.action_schema import Action
from planning.action_types import (
    RETRIEVE,
    REPAIR,
    VALIDATE,
    RUN_BACKEND_TESTS,
    RUN_FRONTEND_BUILD,
)


class FailureAnalysisEngine:
    """
    Converts a list of TestFailure dicts (from failure_parser.py) into
    an ordered list of REPAIR Actions with concrete file targets.

    Usage in executor dispatch:
        result = self.tests.run_backend_tests()
        failures = result.get("failures", [])
        if failures:
            actions = self.failure_engine.build_repair_actions(failures, state)
            state_manager.push_executions(actions)
    """

    # =========================================================
    # MAIN
    # =========================================================

    def build_repair_actions(
        self,
        failures: List[Dict[str, Any]],
        state,
        state_manager=None,
    ) -> List[Action]:
        """
        Given a list of structured failure dicts, return REPAIR actions
        with `targets` metadata populated from `likely_source_files`.

        Also writes `state.test_failure_targets` so repair_from_context
        and RepairEngine can read them without re-parsing.
        """

        # Collect all unique likely source files across all failures,
        # preserving the order in which they appear (first failure first).
        all_targets: List[str] = []
        seen: set = set()

        for failure in failures:
            for path in failure.get("likely_source_files", []):
                if path and path not in seen:
                    seen.add(path)
                    all_targets.append(path)

        # Fallback: if no source files resolved, use stack frames as hints
        if not all_targets:
            for failure in failures:
                for frame in failure.get("stack_frames", [])[:3]:
                    hint = frame.split(":")[0]  # "EmployeeService.java"
                    if hint not in seen:
                        seen.add(hint)
                        all_targets.append(hint)

        # Write back to state so other components can read without re-parsing
        if state is not None and hasattr(state, "test_failure_targets"):
            state.test_failure_targets = all_targets[:10]
        elif state is not None:
            try:
                object.__setattr__(state, "test_failure_targets", all_targets[:10])
            except Exception:
                pass

        actions: List[Action] = []

        if not all_targets:
            # No specific targets resolved — fall back to retrieval-guided repair
            error_text = self._summarise_failures(failures)
            actions.append(Action(
                action_type=RETRIEVE,
                title="Retrieve failure context",
                target=error_text,
                reasoning="No source files resolved from stack trace — search by error text",
                priority=1,
            ))
            actions.append(Action(
                action_type=REPAIR,
                title="Repair from retrieved context",
                target="repair failure",
                reasoning="Guiding repair from retrieval since source files unresolved",
                priority=2,
                blocking=True,
                metadata={"targets": []},
            ))
            return actions

        # Build one REPAIR action per unique target file (up to 5)
        for idx, target_path in enumerate(all_targets[:5]):
            # Human-readable failure summary for the relevant failure(s)
            relevant = [
                f for f in failures
                if target_path in f.get("likely_source_files", [])
            ]
            description = self._summarise_failures(relevant or failures[:1])

            actions.append(Action(
                action_type=REPAIR,
                title=f"Repair {self._basename(target_path)} — {description[:80]}",
                target=target_path,
                reasoning=(
                    f"Stack trace points to {self._basename(target_path)}: "
                    f"{description}"
                ),
                priority=idx + 1,
                blocking=True,
                metadata={
                    "targets": [target_path],
                    "failure_description": description,
                    "all_failure_targets": all_targets,
                },
            ))

        # Always validate + re-run tests after repairs
        actions.append(Action(
            action_type=VALIDATE,
            title="Validate repaired files",
            target="post-repair validation",
            reasoning="Ensure repairs are syntactically correct",
            priority=len(all_targets[:5]) + 1,
        ))

        return actions

    # =========================================================
    # HELPERS
    # =========================================================

    def _summarise_failures(self, failures: List[Dict[str, Any]]) -> str:
        """Short human-readable summary of failures for action titles."""
        parts = []
        for f in failures[:3]:
            error_type = f.get("error_type", "")
            message = f.get("message", "")
            if error_type and message:
                parts.append(f"{error_type}: {message[:60]}")
            elif message:
                parts.append(message[:60])
        return "; ".join(parts) if parts else "test failure"

    def _basename(self, path: str) -> str:
        """Return just the filename from a path string."""
        import os
        return os.path.basename(path)

    # =========================================================
    # LOOP DETECTION HELPERS
    # =========================================================

    def is_same_failure_repeated(
        self,
        current_failures: List[Dict],
        previous_failures: List[Dict],
    ) -> bool:
        """
        Returns True if the same error types + source files appeared in
        both the current and previous failure set — indicating the repair
        did not change anything useful.
        """
        def fingerprint(failures):
            return frozenset(
                (f.get("error_type", ""), tuple(f.get("likely_source_files", [])))
                for f in failures
            )

        return fingerprint(current_failures) == fingerprint(previous_failures)
