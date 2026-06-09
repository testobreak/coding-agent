# planning/plan_compiler.py
#
# Deterministic Plan Compiler. Compiles a ContextPackage into an ExecutionPlan DAG
# using strategy-driven templates. The LLM is never consulted.

from typing import List, Dict, Any, Optional
from planning.task_types import TaskType
from planning.task_node import TaskNode
from planning.execution_plan import ExecutionPlan
from planning.planning_strategy import PlanningStrategy
from planning.action_schema import Action

from planning.task_graph import TaskGraph, SymbolRef

class PlanCompiler:
    """
    Deterministic compiler that converts a ContextPackage into an ExecutionPlan.

    The LLM is NOT in this path. Strategy selection and DAG construction
    are fully rule-based using the rich context already assembled by the
    ContextBuilder subsystem.
    """

    def build_graph(self, context) -> TaskGraph:
        """
        Builds the TaskGraph domain model from the ContextPackage.
        """
        strategy = PlanningStrategy.from_context(context)

        # Resolve primary target info
        primary_fqn = None
        primary_file = None
        if context.primary_symbol:
            primary_fqn = context.primary_symbol.fqn
            primary_file = context.primary_symbol.file_path

        # Collect caller/callee/test FQNs from the package
        caller_fqns = [c.fqn for c in getattr(context, "callers", [])]
        callee_fqns = [c.fqn for c in getattr(context, "callees", [])]
        test_fqns = [t.fqn for t in getattr(context, "related_tests", [])]
        risk_score = getattr(context, "risk_score", 0.0)

        # Dispatch to strategy-specific DAG builder
        if strategy == PlanningStrategy.FEATURE:
            tasks = self._build_feature_dag(primary_fqn, primary_file, test_fqns, risk_score)
        elif strategy == PlanningStrategy.BUGFIX:
            tasks = self._build_bugfix_dag(primary_fqn, primary_file, test_fqns, risk_score)
        elif strategy == PlanningStrategy.REFACTOR:
            tasks = self._build_refactor_dag(primary_fqn, primary_file, caller_fqns, test_fqns, risk_score)
        elif strategy == PlanningStrategy.TEST_ONLY:
            tasks = self._build_test_only_dag(primary_fqn, primary_file, test_fqns)
        elif strategy == PlanningStrategy.ANALYSIS:
            tasks = self._build_analysis_dag(primary_fqn)
        elif strategy == PlanningStrategy.REPAIR:
            tasks = self._build_repair_dag(primary_fqn, primary_file, test_fqns, risk_score, context)
        else:
            tasks = self._build_feature_dag(primary_fqn, primary_file, test_fqns, risk_score)

        symbol_ctx = None
        if context.primary_symbol:
            try:
                from context.context_builder import ContextBuilder
                builder = ContextBuilder(retrieval_pipeline=None)
                symbol_ctx = builder.build_symbol_context_package(context.primary_symbol)
            except Exception as e:
                print(f"[PlanCompiler] SymbolContextPackage compilation warning: {e}")

        graph = TaskGraph()
        graph.metadata["goal"] = context.goal
        graph.metadata["strategy"] = strategy.value
        if symbol_ctx:
            graph.metadata["symbol_context"] = symbol_ctx.to_dict()

        for task in tasks:
            task.repository_id = "com.hrms"
            if task.target_symbol:
                symbol_refs = []
                if symbol_ctx:
                    all_handles = [symbol_ctx.target_symbol] + symbol_ctx.callers + symbol_ctx.callees + symbol_ctx.tests + symbol_ctx.interfaces + symbol_ctx.implementations + symbol_ctx.related_symbols
                    for handle in all_handles:
                        if handle and (handle.fqn == task.target_symbol or handle.fqn.split(".")[-1] == task.target_symbol):
                            symbol_refs.append(SymbolRef(
                                symbol_id=handle.symbol_id,
                                symbol_name=handle.fqn,
                                file_id=handle.file_path,
                                repository_id=task.repository_id
                            ))
                if not symbol_refs:
                    symbol_refs.append(SymbolRef(
                        symbol_id=task.symbol_id or f"fqn:{task.target_symbol}",
                        symbol_name=task.symbol_name or task.target_symbol,
                        file_id=task.file_id or task.payload.get("file_path"),
                        repository_id=task.repository_id
                    ))
                task.symbol_refs = symbol_refs
            graph.add_node(task)

        for task in tasks:
            for dep in task.dependencies:
                graph.add_edge(dep, task.id)

        return graph

    def compile(self, context) -> ExecutionPlan:
        """
        Primary entry point. Accepts a ContextPackage, builds a TaskGraph, and returns an ExecutionPlan.
        """
        strategy = PlanningStrategy.from_context(context)
        print(f"[PlanCompiler] Selected strategy: {strategy.value}")

        # Step 2: Separate planning (graph construction) from scheduling
        graph = self.build_graph(context)

        plan = ExecutionPlan(
            goal=context.goal,
            strategy=strategy,
            tasks=list(graph.nodes.values()),
            graph=graph
        )

        # Step 3 & 4: Compile stages via GraphScheduler
        from planning.graph_scheduler import GraphScheduler
        scheduler = GraphScheduler(plan)
        plan.stages = scheduler.build_execution_stages()

        return plan

    # ------------------------------------------------------------------
    # Strategy DAG Builders
    # ------------------------------------------------------------------

    def _build_feature_dag(
        self, primary_fqn: Optional[str], primary_file: Optional[str],
        test_fqns: List[str], risk_score: float
    ) -> List[TaskNode]:
        """
        FEATURE strategy:
          MODIFY_SYMBOL → [UPDATE_TEST...] → VERIFY_BUILD → RUN_TEST → COMMIT
        """
        tasks = []

        # Modify primary symbol
        modify_id = "modify_0"
        tasks.append(TaskNode(
            id=modify_id,
            type=TaskType.MODIFY_SYMBOL,
            target_symbol=primary_fqn,
            description=f"Implement feature in {primary_fqn or 'target'}",
            dependencies=[],
            payload={"file_path": primary_file}
        ))

        # Update tests if they exist
        test_task_ids = []
        for i, t_fqn in enumerate(test_fqns):
            tid = f"update_test_{i}"
            test_task_ids.append(tid)
            tasks.append(TaskNode(
                id=tid,
                type=TaskType.UPDATE_TEST,
                target_symbol=t_fqn,
                description=f"Update test {t_fqn}",
                dependencies=[modify_id]
            ))

        # Verification gate depends on modify + all test updates
        verify_deps = [modify_id] + test_task_ids
        tasks.append(TaskNode(
            id="build",
            type=TaskType.VERIFY_BUILD,
            description="Verify codebase builds",
            dependencies=verify_deps
        ))

        # Risk-aware lint injection
        if risk_score > 0.5:
            tasks.append(TaskNode(
                id="lint",
                type=TaskType.VERIFY_LINT,
                description="Run lint checks (high risk)",
                dependencies=verify_deps
            ))
            tasks.append(TaskNode(
                id="test",
                type=TaskType.RUN_TEST,
                description="Run test suite",
                dependencies=["build", "lint"]
            ))
        else:
            tasks.append(TaskNode(
                id="test",
                type=TaskType.RUN_TEST,
                description="Run test suite",
                dependencies=["build"]
            ))

        tasks.append(TaskNode(
            id="commit",
            type=TaskType.COMMIT_TRANSACTION,
            description="Commit changes",
            dependencies=["test"]
        ))

        return tasks

    def _build_bugfix_dag(
        self, primary_fqn: Optional[str], primary_file: Optional[str],
        test_fqns: List[str], risk_score: float
    ) -> List[TaskNode]:
        """
        BUGFIX strategy:
          ANALYZE_FAILURE → MODIFY_SYMBOL → VERIFY_BUILD → RUN_TEST → COMMIT
        """
        tasks = [
            TaskNode(
                id="analyze",
                type=TaskType.ANALYZE_FAILURE,
                target_symbol=primary_fqn,
                description=f"Analyze failure in {primary_fqn or 'target'}"
            ),
            TaskNode(
                id="fix_0",
                type=TaskType.MODIFY_SYMBOL,
                target_symbol=primary_fqn,
                description=f"Fix bug in {primary_fqn or 'target'}",
                dependencies=["analyze"],
                payload={"file_path": primary_file}
            ),
            TaskNode(
                id="build",
                type=TaskType.VERIFY_BUILD,
                description="Verify codebase builds",
                dependencies=["fix_0"]
            ),
            TaskNode(
                id="test",
                type=TaskType.RUN_TEST,
                description="Run test suite",
                dependencies=["build"]
            ),
            TaskNode(
                id="commit",
                type=TaskType.COMMIT_TRANSACTION,
                description="Commit fix",
                dependencies=["test"]
            )
        ]

        if risk_score > 0.5:
            tasks.insert(4, TaskNode(
                id="lint",
                type=TaskType.VERIFY_LINT,
                description="Run lint checks (high risk)",
                dependencies=["fix_0"]
            ))
            # Make test depend on lint too
            for t in tasks:
                if t.id == "test":
                    if "lint" not in t.dependencies:
                        t.dependencies.append("lint")

        return tasks

    def _build_refactor_dag(
        self, primary_fqn: Optional[str], primary_file: Optional[str],
        caller_fqns: List[str], test_fqns: List[str], risk_score: float
    ) -> List[TaskNode]:
        """
        REFACTOR strategy:
          [MODIFY_SYMBOL (primary + callers)] → VERIFY_BUILD → RUN_TEST (regression) → COMMIT
        """
        tasks = []

        # Modify primary
        tasks.append(TaskNode(
            id="modify_0",
            type=TaskType.MODIFY_SYMBOL,
            target_symbol=primary_fqn,
            description=f"Refactor {primary_fqn or 'target'}",
            dependencies=[],
            payload={"file_path": primary_file}
        ))

        # Modify affected callers
        modify_ids = ["modify_0"]
        for i, c_fqn in enumerate(caller_fqns[:5]):  # Cap at 5 to limit scope
            mid = f"modify_caller_{i}"
            modify_ids.append(mid)
            tasks.append(TaskNode(
                id=mid,
                type=TaskType.MODIFY_SYMBOL,
                target_symbol=c_fqn,
                description=f"Update caller {c_fqn} after refactor",
                dependencies=["modify_0"]
            ))

        tasks.append(TaskNode(
            id="build",
            type=TaskType.VERIFY_BUILD,
            description="Verify codebase builds after refactor",
            dependencies=modify_ids
        ))

        tasks.append(TaskNode(
            id="test",
            type=TaskType.RUN_TEST,
            description="Run regression test suite",
            dependencies=["build"]
        ))

        tasks.append(TaskNode(
            id="commit",
            type=TaskType.COMMIT_TRANSACTION,
            description="Commit refactor",
            dependencies=["test"]
        ))

        return tasks

    def _build_test_only_dag(
        self, primary_fqn: Optional[str], primary_file: Optional[str],
        test_fqns: List[str]
    ) -> List[TaskNode]:
        """
        TEST_ONLY strategy:
          [UPDATE_TEST...] → RUN_TEST
        """
        tasks = []
        test_ids = []
        for i, t_fqn in enumerate(test_fqns):
            tid = f"update_test_{i}"
            test_ids.append(tid)
            tasks.append(TaskNode(
                id=tid,
                type=TaskType.UPDATE_TEST,
                target_symbol=t_fqn,
                description=f"Update test {t_fqn}",
                dependencies=[]
            ))

        if not test_ids:
            # No known tests — create one for the primary symbol
            tasks.append(TaskNode(
                id="create_test_0",
                type=TaskType.CREATE_SYMBOL,
                target_symbol=f"{primary_fqn}Test" if primary_fqn else "NewTest",
                description="Create new test",
                dependencies=[]
            ))
            test_ids = ["create_test_0"]

        tasks.append(TaskNode(
            id="test",
            type=TaskType.RUN_TEST,
            description="Run test suite",
            dependencies=test_ids
        ))

        return tasks

    def _build_analysis_dag(self, primary_fqn: Optional[str]) -> List[TaskNode]:
        """
        ANALYSIS strategy:
          ANALYZE_FAILURE (single node)
        """
        return [
            TaskNode(
                id="analyze",
                type=TaskType.ANALYZE_FAILURE,
                target_symbol=primary_fqn,
                description=f"Analyze {primary_fqn or 'system state'}"
            )
        ]

    def _build_repair_dag(
        self, primary_fqn: Optional[str], primary_file: Optional[str],
        test_fqns: List[str], risk_score: float, context
    ) -> List[TaskNode]:
        """
        REPAIR strategy (prior failures exist):
          ANALYZE_FAILURE → [REPAIR_SYMBOL...] → VERIFY_BUILD → RUN_TEST → COMMIT
        """
        tasks = [
            TaskNode(
                id="analyze",
                type=TaskType.ANALYZE_FAILURE,
                description="Analyze previous failures",
                payload={"previous_attempts": getattr(context, "previous_attempts", [])}
            )
        ]

        repair_ids = []
        # Primary target repair
        rid = "repair_0"
        repair_ids.append(rid)
        tasks.append(TaskNode(
            id=rid,
            type=TaskType.REPAIR_SYMBOL,
            target_symbol=primary_fqn,
            description=f"Repair {primary_fqn or 'target'}",
            dependencies=["analyze"],
            payload={"file_path": primary_file}
        ))

        tasks.append(TaskNode(
            id="build",
            type=TaskType.VERIFY_BUILD,
            description="Verify build after repair",
            dependencies=repair_ids
        ))

        tasks.append(TaskNode(
            id="test",
            type=TaskType.RUN_TEST,
            description="Run test suite after repair",
            dependencies=["build"]
        ))

        tasks.append(TaskNode(
            id="commit",
            type=TaskType.COMMIT_TRANSACTION,
            description="Commit repair",
            dependencies=["test"]
        ))

        return tasks

    # ------------------------------------------------------------------
    # Backward Compatibility (deprecated)
    # ------------------------------------------------------------------

    def compile_from_intent(self, goal: str, intent_plan: dict) -> ExecutionPlan:
        """
        DEPRECATED: Legacy method that compiles from an LLM-generated intent dict.
        Use compile(context) instead.
        """
        objective = intent_plan.get("objective", "unknown")
        targets = intent_plan.get("targets", [])
        if not targets:
            targets = [intent_plan.get("target", "unknown")]
        failures = intent_plan.get("failures", [])
        target_file = intent_plan.get("target_file")

        tasks = []
        if failures or objective == "repair":
            repair_tasks = []
            for i, target in enumerate(targets):
                repair_tasks.append(TaskNode(
                    id=f"repair_{i}",
                    type=TaskType.REPAIR_FAILURE,
                    target_symbol=target,
                    description=f"Repair failure in {target}",
                    dependencies=["analyze"],
                    payload={"file_path": target_file}
                ))
            tasks = [
                TaskNode(id="analyze", type=TaskType.ANALYZE_FAILURE, description="Analyze previous failures")
            ] + repair_tasks + [
                TaskNode(id="build", type=TaskType.VERIFY_BUILD, description="Verify codebase builds", dependencies=[t.id for t in repair_tasks]),
                TaskNode(id="test", type=TaskType.RUN_TEST, description="Run test suite", dependencies=["build"]),
                TaskNode(id="commit", type=TaskType.COMMIT_TRANSACTION, description="Commit verification changes", dependencies=["test"])
            ]
        elif objective in ["add_feature", "modify", "refactor"]:
            modify_tasks = []
            for i, target in enumerate(targets):
                modify_tasks.append(TaskNode(
                    id=f"modify_{i}",
                    type=TaskType.MODIFY_SYMBOL,
                    target_symbol=target,
                    description=f"Modify symbol/file {target}",
                    dependencies=[],
                    payload={"file_path": target_file}
                ))
            tasks = modify_tasks + [
                TaskNode(id="build", type=TaskType.VERIFY_BUILD, description="Verify codebase builds", dependencies=[t.id for t in modify_tasks]),
                TaskNode(id="test", type=TaskType.RUN_TEST, description="Run test suite", dependencies=["build"]),
                TaskNode(id="commit", type=TaskType.COMMIT_TRANSACTION, description="Commit verification changes", dependencies=["test"])
            ]
        elif objective == "analyze":
            tasks = [
                TaskNode(id="analyze", type=TaskType.ANALYZE_FAILURE, description="Analyze system state")
            ]
        else:
            modify_tasks = []
            for i, target in enumerate(targets):
                modify_tasks.append(TaskNode(
                    id=f"modify_{i}",
                    type=TaskType.MODIFY_SYMBOL,
                    target_symbol=target,
                    description=f"Modify symbol/file {target}",
                    dependencies=[],
                    payload={"file_path": target_file}
                ))
            tasks = modify_tasks + [
                TaskNode(id="build", type=TaskType.VERIFY_BUILD, description="Verify build", dependencies=[t.id for t in modify_tasks])
            ]

        plan = ExecutionPlan(goal=goal, tasks=tasks)
        plan._target_file = target_file
        return plan

    def to_actions(self, plan: ExecutionPlan) -> List[Action]:
        """DEPRECATED: Legacy action bridge."""
        actions = []
        from planning.action_types import (
            MODIFY, RUN_FRONTEND_BUILD, RUN_BACKEND_TESTS, GIT_DIFF, ANALYZE, REPAIR
        )
        
        type_mapping = {
            TaskType.MODIFY_SYMBOL: MODIFY,
            TaskType.CREATE_SYMBOL: MODIFY,
            TaskType.DELETE_SYMBOL: MODIFY,
            TaskType.VERIFY_BUILD: RUN_FRONTEND_BUILD,
            TaskType.RUN_TEST: RUN_BACKEND_TESTS,
            TaskType.VERIFY_CHANGES: GIT_DIFF,
            TaskType.ANALYZE_FAILURE: ANALYZE,
            TaskType.REPAIR_FAILURE: REPAIR,
            TaskType.COMMIT_TRANSACTION: GIT_DIFF
        }
        
        for task in plan.tasks:
            file_path = getattr(plan, "_target_file", None)
            action_type = type_mapping.get(task.type, MODIFY)
            
            actions.append(Action(
                action_type=action_type,
                title=f"Task: {task.type.value}",
                target=task.target_symbol or plan.goal,
                file_path=file_path,
                dependencies=task.dependencies,
                metadata=task.payload
            ))
            
        return actions
