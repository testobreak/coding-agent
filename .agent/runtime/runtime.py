# runtime/runtime.py

import os
from uuid import uuid4

from runtime.execution_engine import (
    ExecutionEngine
)

from runtime.recovery_loop import (
    RecoveryLoop
)

from memory.state_manager import (
    StateManager
)

from execution.executor import (
    Executor
)

from repository.file_manager import (
    FileManager
)

from context.assembler import (
    ContextAssembler
)

from context.prompt_builder import (
    PromptBuilder
)

from llm.ollama_client import (
    OllamaClient
)


class Runtime:

    MAX_ITERATIONS = 20

    def __init__(self):
        # Auto-create database schema if tables are missing
        try:
            from repository_intelligence.db.connection import Base, engine
            from repository_intelligence.models.repository import Repository
            from repository_intelligence.models.file import File
            from repository_intelligence.models.symbol import (
                Symbol,
                Embedding,
                IndexJob,
                RepairPattern,
                SymbolRelationship,
                Test
            )
            Base.metadata.create_all(bind=engine)
            print(f"[Runtime] Database schema initialized with tables: {list(Base.metadata.tables.keys())}")
        except Exception as e:
            print(f"[Runtime] Warning: Database schema auto-creation skipped: {e}")

        self.state_manager = (
            StateManager()
        )

        self.llm = OllamaClient()

        self.context = (
            ContextAssembler()
        )

        self.prompts = (
            PromptBuilder()
        )

        self.file_manager = (
            FileManager("..")
        )

        self.executor = Executor(
            self.file_manager,
            self.state_manager
        )

        self.engine = (
            ExecutionEngine(
                self.executor,
                self.state_manager
            )
        )

        self.recovery = (
            RecoveryLoop(
                self.state_manager,
                self.executor
            )
        )

    # ==========================================
    # START
    # ==========================================

    def start(self):

        print(
            "Autonomous Runtime Started"
        )

        while True:

            goal = input(
                "\nGoal > "
            )

            if goal.lower() in [
                "exit",
                "quit"
            ]:
                break

            self.run_goal(goal)

    # ==========================================
    # TASK
    # ==========================================

    def run_goal(
        self,
        goal
    ):

        task_id = str(uuid4())

        state = (
            self.state_manager.create_task(
                goal=goal,
                task_id=task_id
            )
        )

        # Phase 1: Build rich ContextPackage
        from context.context_builder import ContextBuilder
        builder = ContextBuilder(self.executor.retrieval_pipeline, self.state_manager)
        planning_context = builder.build_planning_context(goal, state)
        
        # Save planning_context.related_files to state.modification_targets
        state.modification_targets = planning_context.related_files

        # Phase 2: Deterministic plan compilation (no LLM)
        from planning.plan_compiler import PlanCompiler
        from planning.plan_validator import PlanValidator

        compiler = PlanCompiler()
        execution_plan = compiler.compile(planning_context)

        # Validate execution plan
        validator = PlanValidator(repo_root=self.file_manager.root)
        validation_errors = validator.validate(execution_plan)
        if validation_errors:
            print("\n[Runtime] PLAN VALIDATION FAILED:")
            for err in validation_errors:
                print(f"  - {err}")
            raise RuntimeError(f"Plan validation failed with errors: {validation_errors}")
        else:
            print("\n[Runtime] Plan validation passed successfully.")

        # Phase 3: Persist plan to disk
        plan_dir = os.path.join(os.path.dirname(__file__), "..", "logs", "plans")
        plan_path = os.path.join(plan_dir, f"{execution_plan.plan_id}.json")
        try:
            execution_plan.save(plan_path)
            print(f"[Runtime] Plan persisted to {plan_path}")
        except Exception as e:
            print(f"[Runtime] Warning: Plan persistence failed: {e}")

        # Save ExecutionPlan to state
        self.state_manager.set_execution_plan(execution_plan)

        # Phase 4: Execute DAG
        iteration = 0

        while (
            iteration
            < self.MAX_ITERATIONS
        ):

            iteration += 1

            state.runtime_memory.total_iterations += 1

            self.engine.run()

            # Check if DAG execution is finished
            plan = self.state_manager.get_execution_plan()
            if plan:
                if plan.is_finished():
                    break
            else:
                recovered = (
                    self.recovery.run()
                )
                if not recovered:
                    break

        # Set final execution state based on DAG success
        plan = self.state_manager.get_execution_plan()
        if plan:
            if plan.is_successful():
                self.state_manager.set_execution_state("COMPLETED")
            else:
                self.state_manager.set_execution_state("FAILED")
        else:
            self.state_manager.set_execution_state("COMPLETED")

        state.status = "completed"

        self.state_manager.save_state()

        print(
            "\nTask Complete"
        )
