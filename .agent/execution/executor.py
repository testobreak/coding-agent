# execution/executor.py

import os
import time
import traceback
from datetime import (
    datetime,
    timezone
)
from typing import List

from context.assembler import ContextAssembler
from context.prompt_builder import PromptBuilder
from memory.execution_history import (
    ExecutionRecord
)
from execution.validators import (
    ExecutionValidator
)
from repository.git_manager import (
    GitManager
)
from repository.patch_manager import (
    PatchManager
)
from repository.write_manager import (
    WriteManager
)
from repository.patch_generator import (
    PatchGenerator
)
from execution.test_runner import (
    TestRunner
)
from execution.compile_validator import CompileValidator
from execution.failure_analysis_engine import FailureAnalysisEngine
from analysis.impact_analyzer import ImpactAnalyzer
from reflection.critic import (
    Critic
)
from reflection.replanner import (
    Replanner
)
from llm.ollama_client import (
    OllamaClient
)
from retrieval.retriever import (
    CodeRetriever
)
from retrieval.retrieval_pipeline import (
    RetrievalPipeline
)


class SubExecutor:

    def __init__(self, executor):
        self.executor = executor
        self.file_manager = executor.file_manager
        self.state_manager = executor.state_manager

    def execute(self, execution):
        tool = execution.get("tool")
        args = execution.get("args", {})
        return self.executor.dispatch(tool, args)


class AnalysisExecutor(SubExecutor):

    def execute(self, execution):
        tool = execution.get("tool")
        args = execution.get("args", {})

        if tool == "summarize_state":
            state = self.state_manager.get_state()
            targets = list(getattr(state, "modification_targets", []) or [])

            if not targets:
                try:
                    from execution.target_ranker import TargetRanker
                    targets = TargetRanker().top_targets(state, n=5)
                except Exception:
                    pass

            file_summaries = []
            for file in targets:
                try:
                    # Execute read_file through the dispatcher to ensure tracking and validation
                    result = self.executor.dispatch("read_file", {"path": file})
                    if isinstance(result, str):
                        content = result
                    elif isinstance(result, dict) and "content" in result:
                        content = result["content"]
                    else:
                        content = self.file_manager.read_file(file)

                    if content:
                        summary = self.summarize_file(file, content)
                        file_summaries.append((file, summary))
                except Exception as e:
                    print(f"[AnalysisExecutor] Failed to summarize {file}: {e}")

            combined_summary = self.combine_summaries(state.goal, file_summaries)

            print("\n  \033[1m\033[36m┌" + "─" * 64 + "┐\033[0m")
            print("  \033[1m\033[36m│  ANALYSIS COMPLETE" + " " * 45 + "│\033[0m")
            print("  \033[1m\033[36m└" + "─" * 64 + "┘\033[0m\n")
            print(combined_summary)
            print()

            return {
                "success": True,
                "goal": state.goal,
                "summary": combined_summary,
                "file_summaries": {f: s for f, s in file_summaries}
            }

        return self.executor.dispatch(tool, args)

    def summarize_file(self, file_path, content):
        prompt = f"""You are a software engineer.
Summarize the following file: {file_path}
Provide an extremely concise summary of maximum 3 bullet points and under 80 words.
Focus strictly on its core role, main exports, and dependencies.

FILE CONTENT:
{content}
"""
        try:
            response = self.executor.modifier.llm.chat([
                {"role": "user", "content": prompt}
            ], role="critic")
            return response.strip()
        except Exception as e:
            return f"Error summarizing file: {e}"

    def combine_summaries(self, goal, file_summaries):
        if not file_summaries:
            return "No files were analyzed."

        summaries_text = ""
        for file, summary in file_summaries:
            summaries_text += f"### File: {file}\n{summary}\n\n"

        prompt = f"""You are a software engineer.
Synthesize a comprehensive architectural summary of the frontend to address the user's goal.
User goal: {goal}

Here are the summaries of the relevant files:
{summaries_text}

Provide a clear, detailed, premium summary of the architecture, dependencies, components, and key entry points, highlighting how they connect.
"""
        try:
            response = self.executor.modifier.llm.chat([
                {"role": "user", "content": prompt}
            ], role="critic")
            return response.strip()
        except Exception as e:
            return f"Error combining summaries: {e}"


class ModificationExecutor(SubExecutor):

    def execute(self, execution):
        tool = execution.get("tool")
        args = execution.get("args", {})
        return self.executor.dispatch(tool, args)


class RepairExecutor(SubExecutor):

    def execute(self, execution):
        tool = execution.get("tool")
        args = execution.get("args", {})
        return self.executor.dispatch(tool, args)


class Executor:

    def __init__(
        self,
        file_manager,
        state_manager
    ):

        self.file_manager = file_manager

        self.state_manager = (
            state_manager
        )

        # Context assembly components
        self.context_assembler = (
            ContextAssembler()
        )

        self.prompt_builder = (
            PromptBuilder()
        )

        # Semantic retrieval
        from retrieval.service import RetrievalFacade
        self.retrieval_facade = RetrievalFacade()
        self.retriever = self.retrieval_facade.retriever
        self.retrieval_pipeline = self.retrieval_facade.pipeline

        self.validator = (
            ExecutionValidator()
        )

        self.git = GitManager(
            file_manager.root
        )

        self.patch_manager = (
            PatchManager(
                file_manager.root
            )
        )

        self.writer = WriteManager(
            file_manager.root
        )

        self.patch_generator = (
            PatchGenerator()
        )

        self.llm = (
            OllamaClient()
        )
        self.edit_executor = None

        self.tests = TestRunner(
            file_manager.root
        )

        self.compile_validator = CompileValidator(
            repo_root=file_manager.root
        )

        self.failure_engine = FailureAnalysisEngine()

        self.impact_analyzer = ImpactAnalyzer(
            repo_root=file_manager.root
        )

        self.critic = Critic()

        self.replanner = Replanner()

    def get_task_type(self) -> str:
        try:
            state = self.state_manager.get_state()
            if getattr(state, "test_failures", None) or getattr(state, "failed_steps", None):
                return "repair"
            elif getattr(state, "task_type", None) == "analysis":
                return "analysis"
        except Exception:
            pass
        return "modification"

    def execute(
        self,
        execution
    ):
        """
        Accepts:
        - ExecutableAction
        - Any object exposing to_dict()
        - Plain dict
        """

        if hasattr(
            execution,
            "to_dict"
        ):
            execution = execution.to_dict()

        elif not isinstance(
            execution,
            dict
        ):
            raise TypeError(
                f"Unsupported execution type: "
                f"{type(execution)}"
            )

        started = time.time()

        if not hasattr(self, "edit_executor") or self.edit_executor is None:
            from editing.edit_executor import EditExecutor
            self.edit_executor = EditExecutor(
                file_manager=self.file_manager,
                state_manager=self.state_manager,
                git_manager=self.git,
                validator=self.validator,
                compile_validator=self.compile_validator,
                test_runner=self.tests,
                impact_analyzer=self.impact_analyzer,
                retrieval_pipeline=self.retrieval_pipeline,
                llm=self.llm,
            )

        tool = execution.get(
            "tool"
        )

        args = execution.get(
            "args",
            {}
        )

        record = ExecutionRecord(
            action_id=execution.get(
                "action_id",
                "unknown"
            ),
            tool=tool,
            status="running",
            input_data=execution
        )

        # Route execution to task-specific sub-executors
        task_type = self.get_task_type()
        if task_type == "analysis":
            sub_exec = AnalysisExecutor(self)
        elif task_type == "repair":
            sub_exec = RepairExecutor(self)
        else:
            sub_exec = ModificationExecutor(self)

        try:

            self.validator.validate_retry(
                execution
            )

            self.validator.validate_execution(
                tool,
                args
            )

            result = sub_exec.execute(execution)

            record.success = True
            record.status = "completed"
            record.output_data = result

            self.state_manager.add_tool_output(
                tool,
                result
            )

            return {
                "success": True,
                "tool": tool,
                "result": result,
                "duration": round(
                    time.time() - started,
                    3
                )
            }

        except Exception as e:

            traceback.print_exc()

            record.success = False
            record.status = "failed"
            record.error = str(e)

            return {
                "success": False,
                "tool": tool,
                "error": str(e)
            }

        finally:

            record.duration_seconds = (
                time.time() - started
            )

            record.completed_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            self.state_manager.add_execution_record(
                record
            )

            self.state_manager.increment_tool_calls()

    def _persist_retrieved_chunks(
        self,
        chunks: List[dict]
    ) -> None:
        """
        Persist unified retrieval chunks into agent state so that
        downstream systems can consume them structurally.
        """
        for chunk in chunks:

            self.state_manager.add_chunk(
                chunk
            )

        if chunks:
            self.state_manager.increment_retrievals()

    def _handle_test_failures(self, test_result: dict) -> None:
        failures = test_result.get('failures', [])
        if not failures:
            return
        state = self.state_manager.get_state()
        print(
            f'[FailureAnalysis] {len(failures)} structured failure(s) '
            f'— generating REPAIR actions.'
        )
        repair_actions = self.failure_engine.build_repair_actions(
            failures=failures,
            state=state,
            state_manager=self.state_manager,
        )
        if repair_actions and hasattr(self.state_manager, 'push_executions'):
            self.state_manager.push_executions(repair_actions)
            print(
                f'[FailureAnalysis] Pushed {len(repair_actions)} REPAIR '
                f'action(s) to execution queue.'
            )
        if hasattr(self.state_manager, 'add_test_failure'):
            for f in failures:
                self.state_manager.add_test_failure(f)

    def dispatch(
        self,
        tool,
        args
    ):

        #
        # filesystem
        #

        if tool == "list_files":

            return self.file_manager.list_files()

        elif tool == "search_code":

            return self.file_manager.search_code(
                args["keyword"]
            )

        elif tool == "semantic_retrieve":

            query = args["query"]

            # Retrieve active goal safely to pass into ranking
            active_goal = ""
            try:
                state = self.state_manager.get_state()
                active_goal = getattr(state, "goal", "")
            except Exception:
                pass

            results = (
                self.retrieval_pipeline
                .retrieve_relevant_chunks(
                    query=query,
                    top_k=8,
                    expand_context=True,
                    goal=active_goal
                )
            )

            chunks = [
                item["chunk"]
                for item in results
            ]

            self._persist_retrieved_chunks(
                chunks
            )

            return results

        elif tool == "read_file":

            return self.file_manager.read_file(
                path=args["path"],
                start=args.get("start"),
                end=args.get("end")
            )

        #
        # git
        #

        elif tool == "git_status":

            return self.git.status()

        elif tool == "git_diff":
            path = args.get("path")
            diff = self.git.diff(path)

            self.validator.validate_diff_size(
                diff
            )

            return diff

        elif tool == "git_commit":

            message = args.get(
                "message",
                "agent update"
            )

            return self.git.commit(
                message
            )

        elif tool == "rollback_file":

            target = args.get(
                "path"
            )

            if not target:
                raise RuntimeError(
                    "path required"
                )

            return self.git.rollback_file(
                target
            )

        elif tool == "rollback_to_commit":

            commit = args.get(
                "commit"
            )

            if not commit:
                commit = self.git.get_last_checkpoint()

            if not commit:
                raise RuntimeError(
                    "No checkpoint commit hash found for rollback"
                )

            return self.git.rollback_to_commit(
                commit
            )

        elif tool == "create_checkpoint":

            return self.git.create_checkpoint(
                args.get(
                    "message",
                    "checkpoint"
                )
            )

        #
        # modifications
        #

        elif tool == "apply_patch":

            patch = args.get(
                "patch"
            )

            if not patch:

                patch = (
                    self.state_manager
                    .get_last_patch()
                )

            if not patch:

                raise RuntimeError(
                    "No patch available"
                )

            return self.patch_manager.apply_patch(
                patch
            )

        elif tool == "write_file":

            # Begin a modification transaction for a write_file operation
            from execution.modification_transaction import ModificationTransaction
            tx = ModificationTransaction(
                git_manager=self.git,
                state_manager=self.state_manager,
                goal=f"Write file {args['path']}"
            )
            tx.begin()
            try:
                result = self.writer.write_file(
                    path=args["path"],
                    content=args["content"]
                )
                if not result.get("success", False):
                    raise RuntimeError("File write failed")
                # Validate syntax after successful write
                self.validator.validate_file_syntax(self.file_manager.resolve_path(args["path"]))
                # Track the modified file and commit transaction
                tx.modified_files.append(args["path"])
                tx.save_to_db()
                tx.commit()
                return result
            except Exception as e:
                # Rollback on any error
                tx.rollback(str(e))
                raise

        elif tool == "modify_file":
            raise RuntimeError(
                "modify_file is permanently disabled. "
                "All edits must go through EditExecutor.execute(edit_plan). "
                "Use the 'execute_edit_plan' or 'modify_symbol' tool instead."
            )

        elif tool == "modify_symbol":
            from editing.models import EditOperation, EditPlan
            op_raw = args.get("operation", "replace_method_body")
            try:
                operation = EditOperation(op_raw)
            except ValueError:
                operation = EditOperation.REPLACE_METHOD_BODY
            plan = EditPlan(
                operation=operation,
                symbol=args["symbol"],
                goal=args["goal"],
                file_path=args.get("path"),
            )
            return self.edit_executor.execute(plan)

        elif tool == "execute_edit_plan":
            from editing.models import EditPlan
            plan = EditPlan.from_dict(args)
            return self.edit_executor.execute(plan)

        elif tool == "generate_modification":
            raise RuntimeError(
                "generate_modification is permanently disabled. "
                "All edits must go through EditExecutor.execute(edit_plan). "
                "Use the 'execute_edit_plan' or 'modify_symbol' tool instead."
            )

        elif tool == "generate_patch":

            payload = args

            if not payload:

                payload = (
                    self.state_manager
                    .get_last_modification()
                )

            if not payload:

                raise RuntimeError(
                    "No modification available"
                )

            patch = (
                self.patch_generator.generate(

                    original_content=
                        payload["original"],

                    modified_content=
                        payload["modified"],

                    path=
                        payload["path"]
                )
            )

            self.validator.validate_patch(
                patch
            )

            self.state_manager.set_last_patch(
                patch
            )

            return {
                "success": True,
                "patch": patch
            }

        #
        # tests
        #

        elif tool == "run_backend_tests":

            return self.tests.run_backend_tests(
                test_filter=args.get("test_filter") or args.get("symbol"),
                touched_files=args.get("touched_files") or ([args.get("path")] if args.get("path") else [])
            )

        elif tool == "run_frontend_tests":

            return self.tests.run_frontend_tests()

        elif tool == "run_frontend_build":

            return self.tests.run_frontend_build()

        #
        # planner helpers
        #

        elif tool == "summarize_state":

            state = (
                self.state_manager
                .get_state()
            )

            return {
                "goal":
                    getattr(
                        state,
                        "goal",
                        None
                    ),

                "completed_steps":
                    len(
                        getattr(
                            state,
                            "completed_steps",
                            []
                        )
                    ),

                "failures":
                    len(
                        getattr(
                            state,
                            "failed_steps",
                            []
                        )
                    ),

                "retrieved_chunks":
                    len(
                        getattr(
                            state,
                            "retrieved_chunks",
                            []
                        )
                    ),

                "tool_outputs":
                    len(
                        getattr(
                            state,
                            "tool_outputs",
                            []
                        )
                    )
            }

        elif tool == "plan_modifications":

            state = (
                self.state_manager
                .get_state()
            )

            return {
                "goal":
                    getattr(
                        state,
                        "goal",
                        None
                    ),

                "touched_files":
                    getattr(
                        state,
                        "touched_files",
                        []
                    ),

                "active_symbols":
                    getattr(
                        state,
                        "active_symbols",
                        []
                    ),

                "recommendation":
                    (
                        "Analyze retrieved "
                        "architecture before "
                        "performing modifications."
                    )
            }

        #
        # reflection
        #

        elif tool == "reflect":

            state = (
                self.state_manager
                .get_state()
            )

            result = (
                self.critic.analyze(
                    state
                )
            )

            if hasattr(
                self.state_manager,
                "add_reflection"
            ):
                self.state_manager.add_reflection(
                    str(result)
                )

            return result

        elif tool == "replan":

            state = (
                self.state_manager
                .get_state()
            )

            actions = (
                self.replanner.replan(
                    state,
                    retrieval_pipeline=self.retrieval_pipeline
                )
            ) or []

            if (
                actions
                and hasattr(
                    self.state_manager,
                    "push_executions"
                )
            ):
                self.state_manager.push_executions(
                    actions
                )

            return {
                "generated_actions":
                    len(actions),

                "actions":
                    actions
            }

        raise RuntimeError(
            f"Unknown tool: {tool}"
        )

    @property
    def modifier(self):
        # Compatibility bridge for legacy tests and graph runtime referencing executor.modifier.llm
        class ModifierCompatBridge:
            def __init__(self, llm):
                self.llm = llm
        return ModifierCompatBridge(self.llm)

