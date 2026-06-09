# reflection/replanner.py

from planning.planner import (
    Planner
)

from reflection.critic import (
    Critic
)

from reflection.repair_engine import (
    RepairEngine
)


class Replanner:

    def __init__(self):

        self.planner = Planner()

        self.critic = Critic()

        self.repair_engine = (
            RepairEngine()
        )

    # =====================================================
    # MAIN
    # =====================================================

    def replan(
        self,
        state,
        retrieval_pipeline=None
    ):

        # Resolve retrieval pipeline
        if retrieval_pipeline is None:
            try:
                from retrieval.retriever import CodeRetriever
                from retrieval.retrieval_pipeline import RetrievalPipeline
                import os
                # Find repo root
                repo_root = os.getcwd()
                if not os.path.exists(os.path.join(repo_root, ".git")):
                    repo_root = os.path.dirname(repo_root)
                retriever = CodeRetriever(repo_root=repo_root)
                retrieval_pipeline = RetrievalPipeline(retriever)
            except Exception as e:
                print(f"[Replanner] Warning: Failed to initialize fallback retrieval pipeline: {e}")

        # Instantiate ContextBuilder and build PlanningContext
        from context.context_builder import ContextBuilder
        builder = ContextBuilder(retrieval_pipeline)
        planning_context = builder.build_planning_context(state.goal, state)

        # Propagate related files back to state modification targets to align execution
        if hasattr(state, "modification_targets"):
            state.modification_targets = planning_context.related_files

        critique = self.critic.analyze(
            state
        )

        severity = critique.get(
            "severity",
            "low"
        )

        reflections = critique.get(
            "reflections",
            []
        )

        # =============================================
        # CRITICAL FAILURE
        # =============================================

        if severity == "critical":

            return self.build_critical_plan(
                state,
                critique
            )

        # =============================================
        # LOOP DETECTED
        # =============================================

        if any(

            "loop" in r.lower()

            for r in reflections
        ):

            return self.build_loop_breaking_plan(
                state
            )

        # =============================================
        # HIGH FAILURE
        # =============================================

        if severity == "high":

            return (
                self.repair_engine
                .build_repair_actions(
                    state
                )
            )

        # =============================================
        # DEFAULT REPLAN
        # =============================================

        from planning.plan_compiler import PlanCompiler
        intent_plan = self.planner.create_intent_plan(planning_context)
        compiler = PlanCompiler()
        execution_plan = compiler.compile(state.goal, intent_plan)
        return compiler.to_actions(execution_plan)

    # =====================================================
    # CRITICAL RECOVERY
    # =====================================================

    def build_critical_plan(
        self,
        state,
        critique
    ):

        from planning.action_schema import (
            Action
        )

        from planning.action_types import (
            ROLLBACK,
            RETRIEVE,
            ANALYZE
        )

        return [

            Action(

                action_type=ROLLBACK,

                title="Rollback unsafe changes",

                target="rollback",

                reasoning=(
                    "Critical failure recovery"
                ),

                priority=1,

                blocking=True
            ),

            Action(

                action_type=RETRIEVE,

                title="Retrieve stable context",

                target=state.goal,

                reasoning=(
                    "Rebuild repository understanding"
                ),

                priority=2
            ),

            Action(

                action_type=ANALYZE,

                title="Analyze critical failure",

                target="critical recovery",

                reasoning=(
                    "Determine root cause"
                ),

                priority=3
            )
        ]

    # =====================================================
    # LOOP BREAKING
    # =====================================================

    def build_loop_breaking_plan(
        self,
        state
    ):

        from planning.action_schema import (
            Action
        )

        from planning.action_types import (
            RETRIEVE,
            ANALYZE,
            REFLECT
        )

        return [

            Action(

                action_type=REFLECT,

                title="Reflect on repeated failures",

                target="loop analysis",

                reasoning=(
                    "Break repeated execution cycle"
                ),

                priority=1
            ),

            Action(

                action_type=RETRIEVE,

                title="Retrieve alternative context",

                target=state.goal,

                reasoning=(
                    "Gather additional context"
                ),

                priority=2
            ),

            Action(

                action_type=ANALYZE,

                title="Analyze alternative strategy",

                target="alternative approach",

                reasoning=(
                    "Generate new execution path"
                ),

                priority=3
            )
        ]
