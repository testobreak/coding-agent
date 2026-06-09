# reflection/critic.py

from typing import Dict, Any

from memory.task_state import (
    TaskState
)


class Critic:

    def __init__(self):

        self.max_recent_failures = 5

    # =====================================================
    # MAIN
    # =====================================================

    def analyze(
        self,
        state: TaskState
    ) -> Dict[str, Any]:

        failures = (
            state.failed_steps[
                -self.max_recent_failures:
            ]
        )

        reflections = []

        severity = "low"

        # =============================================
        # FAILURE ANALYSIS
        # =============================================

        if failures:

            severity = self.classify_severity(
                failures
            )

            reflections.extend(
                self.extract_failure_patterns(
                    failures
                )
            )

        # =============================================
        # LOOP DETECTION
        # =============================================

        if self.detect_execution_loop(
            state
        ):

            reflections.append(
                "Execution loop detected."
            )

            severity = "high"

        # =============================================
        # RETRIEVAL QUALITY
        # =============================================

        retrieval_issue = (
            self.detect_retrieval_issues(
                state
            )
        )

        if retrieval_issue:

            reflections.append(
                retrieval_issue
            )

        # =============================================
        # TEST INSTABILITY
        # =============================================

        if len(state.test_failures) >= 3:

            reflections.append(
                "Persistent test failures detected."
            )

            severity = "high"

        return {

            "severity": severity,

            "reflections": reflections,

            "recommended_action":
                self.recommend_action(
                    severity,
                    reflections
                )
        }

    # =====================================================
    # FAILURE PATTERNS
    # =====================================================

    def extract_failure_patterns(
        self,
        failures
    ):

        patterns = []

        combined = (
            " ".join(failures)
            .lower()
        )

        if "syntax" in combined:

            patterns.append(
                "Syntax-related failures detected."
            )

        if "import" in combined:

            patterns.append(
                "Dependency/import issues detected."
            )

        if "test" in combined:

            patterns.append(
                "Test execution instability detected."
            )

        if "timeout" in combined:

            patterns.append(
                "Timeout instability detected."
            )

        return patterns

    # =====================================================
    # LOOP DETECTION
    # =====================================================

    def detect_execution_loop(
        self,
        state
    ):

        recent = state.completed_steps[-8:]

        if len(recent) < 8:
            return False

        unique = len(set(recent))

        return unique <= 2

    # =====================================================
    # RETRIEVAL ISSUES
    # =====================================================

    def detect_retrieval_issues(
        self,
        state
    ):

        if (
            len(state.retrieved_chunks)
            == 0
        ):

            return (
                "No retrieval context available."
            )

        if (
            len(state.retrieved_chunks)
            > 50
        ):

            return (
                "Retrieval overload detected."
            )

        return None

    # =====================================================
    # SEVERITY
    # =====================================================

    def classify_severity(
        self,
        failures
    ):

        text = (
            " ".join(failures)
            .lower()
        )

        if any(
            word in text
            for word in [
                "crash",
                "fatal",
                "corrupt",
                "rollback"
            ]
        ):

            return "critical"

        if any(
            word in text
            for word in [
                "test",
                "syntax",
                "failure"
            ]
        ):

            return "high"

        return "medium"

    # =====================================================
    # RECOMMENDATIONS
    # =====================================================

    def recommend_action(
        self,
        severity,
        reflections
    ):

        if severity == "critical":

            return (
                "Rollback or isolate modifications."
            )

        if severity == "high":

            return (
                "Initiate repair workflow."
            )

        if any(
            "loop" in r.lower()
            for r in reflections
        ):

            return (
                "Trigger replanning."
            )

        return (
            "Continue execution."
        )
