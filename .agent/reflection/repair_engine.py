# reflection/repair_engine.py

from typing import List

from planning.action_schema import (
    Action
)

from planning.action_types import (
    RETRIEVE,
    ANALYZE,
    REPAIR,
    VALIDATE,
    TEST
)

class RepairEngine:

    def build_repair_actions(
        self,
        state
    ) -> List[Action]:

        failures = (
            state.failed_steps[-5:]
        )

        actions = []

        # =============================================
        # RETRIEVE CONTEXT
        # =============================================

        actions.append(

            Action(

                action_type=RETRIEVE,

                title="Retrieve failure context",

                target=" ".join(failures),

                reasoning=(
                    "Gather related failure context"
                ),

                priority=1
            )
        )

        # =============================================
        # ANALYZE ROOT CAUSE
        # =============================================

        actions.append(

            Action(

                action_type=ANALYZE,

                title="Analyze repair strategy",

                target="repair analysis",

                reasoning=(
                    "Identify minimal safe repair"
                ),

                priority=2
            )
        )

        # =============================================
        # REPAIR
        # =============================================

        actions.append(

            Action(

                action_type=REPAIR,

                title="Repair failing implementation",

                target="repair code",

                reasoning=(
                    "Fix failing behavior"
                ),

                priority=3,

                blocking=True
            )
        )

        # =============================================
        # VALIDATE
        # =============================================

        actions.append(

            Action(

                action_type=VALIDATE,

                title="Validate repairs",

                target="repair validation",

                reasoning=(
                    "Ensure repair safety"
                ),

                priority=4
            )
        )

        # =============================================
        # TESTS
        # =============================================

        actions.append(

            Action(

                action_type=TEST,

                title="Re-run tests",

                target="repair verification",

                reasoning=(
                    "Verify repair success"
                ),

                priority=5
            )
        )

        return actions

    # =====================================================
    # REPAIR HEURISTICS
    # =====================================================

    def classify_failure(
        self,
        failure_text
    ):

        lowered = failure_text.lower()

        if "syntax" in lowered:
            return "syntax"

        if "import" in lowered:
            return "dependency"

        if "test" in lowered:
            return "test"

        if "timeout" in lowered:
            return "timeout"

        return "general"
