# AGENT REPOSITORY EXPORT


====================================================================================================
PATH: context\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: context\assembler.py
====================================================================================================

```python
# context/assembler.py

from typing import Dict, Any, List

from memory.task_state import (
    TaskState
)

from context.compression import (
    ContextCompressor
)


class ContextAssembler:

    def __init__(
        self,
        max_chunks: int = 6,
        max_failures: int = 5,
        max_executions: int = 5,
        max_reflections: int = 3,
        max_history: int = 10
    ):

        self.max_chunks = max_chunks

        self.max_failures = max_failures

        self.max_executions = max_executions

        self.max_reflections = (
            max_reflections
        )

        self.max_history = max_history

        self.compressor = (
            ContextCompressor()
        )

    # =====================================================
    # MAIN
    # =====================================================

    def build(
        self,
        state: TaskState
    ) -> Dict[str, Any]:

        retrieved_chunks = (
            self.compressor.compress_chunks(

                state.retrieved_chunks[
                    -self.max_chunks:
                ]
            )
        )

        recent_outputs = (
            self.compressor
            .compress_tool_outputs(

                state.tool_outputs[-5:]
            )
        )

        return {

            # =============================================
            # CORE
            # =============================================

            "goal":
                state.goal,

            "status":
                state.status,

            "current_step":
                state.current_step,

            # =============================================
            # ACTIVE EXECUTION
            # =============================================

            "pending_executions":

                state.pending_executions[
                    :self.max_executions
                ],

            "current_plan":

                state.current_plan[-10:],

            # =============================================
            # FAILURES
            # =============================================

            "failed_steps":

                state.failed_steps[
                    -self.max_failures:
                ],

            "test_failures":

                state.test_failures[
                    -self.max_failures:
                ],

            "repair_history":

                state.repair_history[-5:],

            # =============================================
            # RETRIEVAL
            # =============================================

            "retrieved_chunks":
                retrieved_chunks,

            "active_symbols":

                state.active_symbols[-20:],

            "touched_files":

                state.touched_files[-20:],

            # =============================================
            # MODIFICATION HISTORY
            # =============================================

            "modification_targets":
                getattr(state, "modification_targets", [])[-20:],

            "modified_files":
                getattr(state, "modified_files", [])[-20:],

            "generated_code":
                getattr(state, "generated_code", [])[-10:],

            # =============================================
            # MEMORY
            # =============================================

            "reflections":

                state.reflections[
                    -self.max_reflections:
                ],

            "architecture_notes":

                state.architecture_notes[
                    -10:
                ],

            # =============================================
            # EXECUTION HISTORY
            # =============================================

            "recent_tool_outputs":
                recent_outputs,

            "execution_history":

                state.execution_history[
                    -self.max_history:
                ],

            # =============================================
            # RUNTIME METRICS
            # =============================================

            "runtime_memory": {

                "iterations":
                    state.runtime_memory
                    .total_iterations,

                "tool_calls":
                    state.runtime_memory
                    .tool_call_count,

                "retrievals":
                    state.runtime_memory
                    .retrieval_count,

                "repairs":
                    state.runtime_memory
                    .repair_count,

                "runtime_errors":
                    state.runtime_memory
                    .runtime_errors
            },

            # =============================================
            # LOOP DETECTION
            # =============================================

            "loop_warning":
                self.detect_loops(state)
        }

    # =====================================================
    # LOOP DETECTION
    # =====================================================

    def detect_loops(
        self,
        state: TaskState
    ):

        recent = state.completed_steps[-6:]

        if len(recent) < 6:
            return False

        unique = len(set(recent))

        return unique <= 2
```


====================================================================================================
PATH: context\compression.py
====================================================================================================

```python
# context/compression.py

from typing import List, Dict, Any


class ContextCompressor:

    def __init__(
        self,
        max_chunk_chars=4000,
        max_tool_output_chars=2000
    ):

        self.max_chunk_chars = max_chunk_chars

        self.max_tool_output_chars = (
            max_tool_output_chars
        )

    # =====================================================
    # CHUNK COMPRESSION
    # =====================================================

    def compress_chunks(
        self,
        chunks: List[Dict[str, Any]]
    ):

        compressed = []

        seen = set()

        for chunk in chunks:

            chunk_id = chunk.get(
                "chunk_id"
            )

            if chunk_id in seen:
                continue

            seen.add(chunk_id)

            code = (
                chunk.get("code")
                or chunk.get("content")
                or ""
            )

            compressed.append({

                "chunk_id":
                    chunk_id,

                "file":
                    chunk.get("file", ""),

                "symbol":
                    chunk.get("name", ""),

                "type":
                    chunk.get("type", ""),

                "score":
                    round(
                        chunk.get("score", 0),
                        4
                    ),

                "content":
                    self.truncate(
                        code,
                        self.max_chunk_chars
                    )
            })

        return compressed

    # =====================================================
    # TOOL OUTPUT COMPRESSION
    # =====================================================

    def compress_tool_outputs(
        self,
        outputs
    ):

        compressed = []

        for output in outputs:

            compressed.append({

                "tool":
                    output.get("tool"),

                "status":
                    output.get("status"),

                "result":
                    self.truncate(
                        str(
                            output.get(
                                "result",
                                ""
                            )
                        ),
                        self.max_tool_output_chars
                    )
            })

        return compressed

    # =====================================================
    # TRUNCATION
    # =====================================================

    def truncate(
        self,
        text,
        limit
    ):

        if not text:
            return ""

        if len(text) <= limit:
            return text

        return (
            text[:limit]
            + "\n\n...[TRUNCATED]..."
        )
```


====================================================================================================
PATH: context\prompt_builder.py
====================================================================================================

```python
# context/prompt_builder.py

from typing import Dict, Any

import json


class PromptBuilder:

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================

    def build_system_prompt(self):

        return """
You are an autonomous software engineering agent.

Your objectives:

- analyze repositories
- retrieve relevant code
- execute modifications safely
- validate architecture consistency
- repair failures autonomously
- avoid regressions
- minimize unnecessary edits

==================================================
EXECUTION RULES
==================================================

Always:

- prioritize active failures
- use retrieved code context
- preserve architecture
- prefer minimal diffs
- avoid speculative rewrites
- avoid duplicate modifications
- validate before major edits

==================================================
RETRIEVAL RULES
==================================================

Never modify code before:

1. retrieving related context
2. understanding dependencies
3. analyzing surrounding patterns

==================================================
FAILURE HANDLING
==================================================

If tests fail:

1. analyze root cause
2. identify minimal repair
3. avoid unrelated changes
4. preserve working behavior

==================================================
LOOP PREVENTION
==================================================

Avoid repeating:

- identical retrievals
- identical analyses
- repeated failed repairs

If stuck:
- replan
- change strategy
- narrow scope

==================================================
OUTPUT RULES
==================================================

Return structured reasoning.

Prefer:
- minimal actions
- high-confidence operations
- architecture-safe execution
"""

    # =====================================================
    # EXECUTION PROMPT
    # =====================================================

    def build_execution_prompt(
        self,
        context: Dict[str, Any]
    ) -> str:

        return f"""
==================================================
TASK CONTEXT
==================================================

{json.dumps(
    context,
    indent=2
)}

==================================================
EXECUTION OBJECTIVES
==================================================

1. Analyze current execution state
2. Prioritize failures first
3. Determine highest-value next step
4. Avoid redundant retrievals
5. Avoid unnecessary modifications
6. Preserve repository architecture
7. Prefer minimal safe changes
8. Detect risky operations
9. Avoid execution loops

==================================================
RESPONSE EXPECTATIONS
==================================================

Your response should:

- reason about current state
- use retrieved context
- identify blockers
- minimize risk
- progress the task safely
"""
```


====================================================================================================
PATH: execution\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: execution\action_compiler.py
====================================================================================================

```python
# execution/action_compiler.py

from typing import List

from planning.action_schema import (
    Action
)

from planning.action_types import *

from execution.executable_action import (
    ExecutableAction
)


class ActionCompiler:

    # =====================================================
    # MAIN
    # =====================================================

    def compile(
        self,
        actions: List[Action]
    ) -> List[ExecutableAction]:

        compiled = []

        for action in actions:

            compiled.extend(
                self.expand_action(
                    action
                )
            )

        return self.sort_by_priority(
            compiled
        )

    # =====================================================
    # EXPANSION
    # =====================================================

    def expand_action(
        self,
        action: Action
    ):

        action_type = (
            action.action_type
        )

        # =============================================
        # RETRIEVE
        # =============================================

        if action_type == RETRIEVE:

            return [

                self.build_action(

                    tool="semantic_retrieve",

                    action=action,

                    args={
                        "query":
                            action.target
                            or ""
                    }
                )
            ]

        # =============================================
        # ANALYZE
        # =============================================

        elif action_type == ANALYZE:

            return [

                self.build_action(

                    tool="list_files",

                    action=action
                )
            ]

        # =============================================
        # MODIFY
        # =============================================

elif action_type == MODIFY:

    if not action.file_path:

        raise RuntimeError(
            "MODIFY action requires file_path"
        )

    return [

        self.build_action(

            tool="create_checkpoint",

            action=action,

            args={
                "message":
                    f"checkpoint:{action.file_path}"
            },

            priority_boost=-2
        ),

        self.build_action(

            tool="modify_file",

            action=action,

            args={

                "path":
                    action.file_path,

                "goal":
                    action.target
                    or action.reasoning
                    or ""
            }
        )
    ]

        # =============================================
        # PATCH
        # =============================================

        elif action_type == PATCH:

            return [

                self.build_action(

                    tool="apply_patch",

                    action=action,

                    args=action.metadata or {}
                )
            ]

        # =============================================
        # WRITE FILE
        # =============================================

        elif action_type == WRITE_FILE:

            return [

                self.build_action(

                    tool="write_file",

                    action=action,

                    args=action.metadata or {}
                )
            ]

        # =============================================
        # GENERATE PATCH
        # =============================================

        elif action_type == GENERATE_PATCH:

            return [

                self.build_action(

                    tool="generate_patch",

                    action=action,

                    args=action.metadata or {}
                )
            ]

        # =============================================
        # GENERATE MODIFICATION
        # =============================================

        elif action_type == GENERATE_MODIFICATION:

            return [

                self.build_action(

                    tool="generate_modification",

                    action=action,

                    args=action.metadata or {}
                )
            ]

        # =============================================
        # VALIDATE
        # =============================================

elif action_type == VALIDATE:

    return [

        self.build_action(
            tool="git_diff",
            action=action,
            priority_boost=-2
        ),

        self.build_action(
            tool="run_backend_tests",
            action=action,
            priority_boost=-1
        ),

        self.build_action(
            tool="run_frontend_build",
            action=action
        )
    ]

        # =============================================
        # TEST
        # =============================================

        elif action_type == TEST:

            return [

                self.build_action(

                    tool="run_backend_tests",

                    action=action
                )
            ]

        # =============================================
        # RUN BACKEND TESTS
        # =============================================

        elif action_type == RUN_BACKEND_TESTS:

            return [

                self.build_action(

                    tool="run_backend_tests",

                    action=action
                )
            ]

        # =============================================
        # RUN FRONTEND TESTS
        # =============================================

        elif action_type == RUN_FRONTEND_TESTS:

            return [

                self.build_action(

                    tool="run_frontend_tests",

                    action=action
                )
            ]

        # =============================================
        # RUN FRONTEND BUILD
        # =============================================

        elif action_type == RUN_FRONTEND_BUILD:

            return [

                self.build_action(

                    tool="run_frontend_build",

                    action=action
                )
            ]

        # =============================================
        # GIT STATUS
        # =============================================

        elif action_type == GIT_STATUS:

            return [

                self.build_action(

                    tool="git_status",

                    action=action
                )
            ]

        # =============================================
        # GIT DIFF
        # =============================================

        elif action_type == GIT_DIFF:

            return [

                self.build_action(

                    tool="git_diff",

                    action=action
                )
            ]

        # =============================================
        # ROLLBACK
        # =============================================

        elif action_type == ROLLBACK:

            if not action.file_path:

                return []

            return [

                self.build_action(

                    tool="rollback_file",

                    action=action,

                    args={
                        "path":
                            action.file_path
                    }
                )
            ]

        # =============================================
        # REPAIR
        # =============================================

elif action_type == REPAIR:

    executions = []

    #
    # Rebuild failure context
    #
    executions.append(

        self.build_action(

            tool="semantic_retrieve",

            action=action,

            args={
                "query":
                    action.target
                    or action.reasoning
                    or "repair failure"
            },

            priority_boost=-2
        )
    )

    #
    # Attempt repair on known targets
    #
    repair_targets = (
        action.metadata.get(
            "targets",
            []
        )
    )

    for path in repair_targets:

        executions.append(

            self.build_action(

                tool="modify_file",

                action=action,

                args={
                    "path": path,
                    "goal":
                        action.target
                        or "repair failure"
                },

                priority_boost=-1
            )
        )

    #
    # Validate repair
    #
    executions.append(

        self.build_action(
            tool="git_diff",
            action=action
        )
    )

    #
    # Re-run tests
    #
    executions.append(

        self.build_action(
            tool="run_backend_tests",
            action=action
        )
    )

    return executions

        # =============================================
        # SUMMARIZE
        # =============================================

        elif action_type == SUMMARIZE:

            return [

                self.build_action(

                    tool="summarize_state",

                    action=action
                )
            ]

        # =============================================
        # MODIFICATION PLANNING
        # =============================================

        elif action_type == MODIFICATION_PLANNING:

            return [

                self.build_action(

                    tool="plan_modifications",

                    action=action
                )
            ]

        # =============================================
        # REFLECT
        # =============================================

        elif action_type == REFLECT:

            return [

                self.build_action(

                    tool="reflect",

                    action=action
                )
            ]

        # =============================================
        # REPLAN
        # =============================================

        elif action_type == REPLAN:

            return [

                self.build_action(

                    tool="replan",

                    action=action
                )
            ]

        # =============================================
        # UNKNOWN ACTION
        # =============================================

        raise RuntimeError(

            f"Unsupported action type: "
            f"{action_type}"
        )

    # =====================================================
    # BUILD
    # =====================================================

    def build_action(
        self,
        tool,
        action,
        args=None,
        priority_boost=0
    ):

        return ExecutableAction(

            tool=tool,

            args=args or {},

            priority=max(
                0,
                action.priority
                + priority_boost
            ),

            blocking=action.blocking,

            max_retries=(
                action.max_retries
            ),

            metadata={

                "source_action_id":
                    action.action_id,

                "source_action_type":
                    action.action_type,

                "reasoning":
                    action.reasoning,

                "estimated_impact":
                    action.estimated_impact
            }
        )

    # =====================================================
    # SORTING
    # =====================================================

    def sort_by_priority(
        self,
        actions
    ):

        return sorted(

            actions,

            key=lambda x: (

                x.priority,

                x.retries
            )
        )
```


====================================================================================================
PATH: execution\executable_action.py
====================================================================================================

```python
from dataclasses import dataclass, field
from typing import Dict, Any
from uuid import uuid4
from datetime import datetime


@dataclass
class ExecutableAction:

    tool: str

    args: Dict[str, Any]

    priority: int = 1

    status: str = "pending"

    retries: int = 0

    max_retries: int = 3

    blocking: bool = False

    created_at: str = field(
        default_factory=lambda:
        datetime.utcnow().isoformat()
    )

    action_id: str = field(
        default_factory=lambda:
        str(uuid4())
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    # STATE
    # =====================================================

    def mark_running(self):

        self.status = "running"

    def mark_completed(self):

        self.status = "completed"

    def mark_failed(self):

        self.status = "failed"

    def increment_retry(self):

        self.retries += 1

    def can_retry(self):

        return (
            self.retries
            < self.max_retries
        )

    # =====================================================
    # SERIALIZATION
    # =====================================================

    def to_dict(self):

        return {

            "action_id":
                self.action_id,

            "tool":
                self.tool,

            "args":
                self.args,

            "priority":
                self.priority,

            "status":
                self.status,

            "retries":
                self.retries,

            "max_retries":
                self.max_retries,

            "blocking":
                self.blocking,

            "created_at":
                self.created_at,

            "metadata":
                self.metadata
        }

    @classmethod
    def from_dict(
        cls,
        data
    ):

        return cls(

            tool=data["tool"],

            args=data.get(
                "args",
                {}
            ),

            priority=data.get(
                "priority",
                1
            ),

            status=data.get(
                "status",
                "pending"
            ),

            retries=data.get(
                "retries",
                0
            ),

            max_retries=data.get(
                "max_retries",
                3
            ),

            blocking=data.get(
                "blocking",
                False
            ),

            created_at=data.get(
                "created_at",
                datetime.utcnow().isoformat()
            ),

            action_id=data.get(
                "action_id",
                str(uuid4())
            ),

            metadata=data.get(
                "metadata",
                {}
            )
        )
```


====================================================================================================
PATH: execution\executor.py
====================================================================================================

```python
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
from reflection.critic import (
    Critic
)
from reflection.replanner import (
    Replanner
)
from llm.modification_engine import (
    ModificationEngine
)
from retrieval.retriever import (
    CodeRetriever
)
from retrieval.retrieval_pipeline import (
    RetrievalPipeline
)


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
        self.retriever = CodeRetriever(
            repo_root=file_manager.root
        )

        self.retrieval_pipeline = (
            RetrievalPipeline(
                self.retriever
            )
        )

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

        self.modifier = (
            ModificationEngine()
        )

        self.tests = TestRunner(
            file_manager.root
        )

        self.critic = Critic()

        self.replanner = Replanner()

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

        try:

            self.validator.validate_retry(
                execution
            )

            self.validator.validate_execution(
                tool,
                args
            )

            result = self.dispatch(
                tool,
                args
            )

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

            results = (
                self.retrieval_pipeline
                .retrieve_relevant_chunks(
                    query=query,
                    top_k=8,
                    expand_context=True
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

            diff = self.git.diff()

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

            return self.writer.write_file(
                path=args["path"],
                content=args["content"]
            )

        elif tool == "modify_file":

            path = args["path"]

            goal = args["goal"]

            try:

                # Stage 1: Generate modified content
                modification_result = self.dispatch(
                    "generate_modification",
                    {
                        "path": path,
                        "goal": goal
                    }
                )

                # Stage 2: Build patch
                patch_result = self.dispatch(
                    "generate_patch",
                    {
                        "path":
                            modification_result["path"],

                        "original":
                            modification_result["original"],

                        "modified":
                            modification_result["modified"]
                    }
                )

                # Stage 3: Apply patch
                apply_result = self.dispatch(
                    "apply_patch",
                    {
                        "patch":
                            patch_result["patch"]
                    }
                )

                success = apply_result.get(
                    "success",
                    False
                )

                if not success:

                    self.dispatch(
                        "rollback_file",
                        {
                            "path": path
                        }
                    )

                # Update state safely on lifecycle success
                state = self.state_manager.get_state()

                if hasattr(state, "modified_files"):

                    if state.modified_files is None:
                        state.modified_files = []

                    if path not in state.modified_files:
                        state.modified_files.append(path)

                if hasattr(state, "generated_code"):

                    if state.generated_code is None:
                        state.generated_code = []

                    state.generated_code.append({
                        "path": path,
                        "content":
                            modification_result["modified"]
                    })

                return {
                    "success": success,
                    "path": path,
                    "patch": patch_result["patch"]
                }

            except Exception:

                try:

                    self.dispatch(
                        "rollback_file",
                        {
                            "path": path
                        }
                    )

                except Exception:
                    pass

                raise

        elif tool == "generate_modification":

            original = (
                self.file_manager.read_file(
                    path=args["path"]
                )
            )

            if original is None:

                raise RuntimeError(
                    f"Unable to read file: "
                    f"{args['path']}"
                )

            state = self.state_manager.get_state()

            context = (
                self.context_assembler.build(
                    state
                )
            )

            execution_context = (
                self.prompt_builder
                .build_execution_prompt(
                    context
                )
            )

            modified = (
                self.modifier.modify_file(
                    goal=args["goal"],
                    file_path=args["path"],
                    original_content=original,
                    execution_context=execution_context,
                    architecture_notes=getattr(
                        state,
                        "architecture_notes",
                        []
                    )
                )
            )

            if not modified:

                raise RuntimeError(
                    "Modification engine returned empty content"
                )

            result = {
                "success": True,
                "path": args["path"],
                "original": original,
                "modified": modified
            }

            self.state_manager.set_last_modification(
                result
            )

            return result

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

            return self.tests.run_backend_tests()

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
                    state
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
```


====================================================================================================
PATH: execution\test_runner.py
====================================================================================================

```python
# execution/test_runner.py

import subprocess

from pathlib import Path


class TestRunner:

    def __init__(self, root="."):

        self.root = Path(root)

    def run_backend_tests(self):

        return self.run_command(
            ["pytest"]
        )

    def run_frontend_tests(self):

        package_json = (
            self.root / "package.json"
        )

        if not package_json.exists():

            return {
                "success": False,
                "error":
                    "package.json not found"
            }

        return self.run_command(
            ["npm", "test", "--", "--run"]
        )

    def run_frontend_build(self):

        package_json = (
            self.root / "package.json"
        )

        if not package_json.exists():

            return {
                "success": False,
                "error":
                    "package.json not found"
            }

        return self.run_command(
            ["npm", "run", "build"]
        )

    def run_command(
        self,
        command,
        timeout=600
    ):

        try:

            result = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                "success":
                    result.returncode == 0,

                "return_code":
                    result.returncode,

                "stdout":
                    result.stdout,

                "stderr":
                    result.stderr
            }

        except subprocess.TimeoutExpired:

            return {
                "success": False,
                "error":
                    "Command timeout"
            }
```


====================================================================================================
PATH: execution\validators.py
====================================================================================================

```python
# execution/validators.py

from pathlib import Path


class ExecutionValidator:

    MAX_DIFF_SIZE = 200000
    MAX_PATCH_SIZE = 500000

    ALLOWED_TOOLS = {
        # filesystem
        "list_files",
        "search_code",
        "read_file",
        "semantic_retrieve",

        # git
        "git_status",
        "git_diff",
        "git_commit",
        "rollback_file",
        "create_checkpoint",

        # modification
        "apply_patch",
        "write_file",
        "generate_patch",
        "generate_modification",
        "modify_file",

        # testing
        "run_backend_tests",
        "run_frontend_tests",
        "run_frontend_build",

        # planner / compiler actions
        "summarize_state",
        "plan_modifications",
        "reflect",
        "replan",
    }

    def validate_retry(
        self,
        execution
    ):
        """
        Accept:
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
            raise RuntimeError(
                "Execution must be dict-like"
            )

        retries = execution.get(
            "retries",
            0
        )

        max_retries = execution.get(
            "max_retries",
            3
        )

        if not isinstance(
            retries,
            int
        ):
            raise RuntimeError(
                "Retry count must be an integer"
            )

        if not isinstance(
            max_retries,
            int
        ):
            raise RuntimeError(
                "Max retries must be an integer"
            )

        if retries < 0:

            raise RuntimeError(
                "Retry count cannot be negative"
            )

        if max_retries < 0:

            raise RuntimeError(
                "Max retries cannot be negative"
            )

        if retries >= max_retries:

            raise RuntimeError(
                "Maximum retries exceeded"
            )

    def validate_execution(
        self,
        tool,
        args
    ):

        if not tool:

            raise RuntimeError(
                "Tool missing"
            )

        if tool not in self.ALLOWED_TOOLS:

            raise RuntimeError(
                f"Tool not allowed: {tool}"
            )

        if args is None:
            args = {}

        if not isinstance(
            args,
            dict
        ):
            raise RuntimeError(
                "Execution args must be a dictionary"
            )

        # =============================================
        # read_file
        # =============================================

        if tool == "read_file":

            path = args.get(
                "path"
            )

            if not path:

                raise RuntimeError(
                    "Missing file path"
                )

            self.validate_path(
                path
            )

        # =============================================
        # rollback_file
        # =============================================

        elif tool == "rollback_file":

            path = args.get(
                "path"
            )

            if not path:

                raise RuntimeError(
                    "Rollback requires path"
                )

            self.validate_path(
                path
            )

        # =============================================
        # apply_patch
        # =============================================

        elif tool == "apply_patch":

            # Allow state fallback
            if not args:
                return

            patch = args.get(
                "patch"
            )

            if not patch:

                raise RuntimeError(
                    "Patch content missing"
                )

        # =============================================
        # write_file
        # =============================================

        elif tool == "write_file":

            path = args.get(
                "path"
            )

            if not path:

                raise RuntimeError(
                    "Missing file path"
                )

            self.validate_path(
                path
            )

            if "content" not in args:

                raise RuntimeError(
                    "Missing file content"
                )

        # =============================================
        # generate_patch
        # =============================================

        elif tool == "generate_patch":

            # Allow state-based execution fallback
            if not args:
                return

            required = [
                "path",
                "original",
                "modified",
            ]

            for key in required:

                value = args.get(key)

                if value is None or value == "":

                    raise RuntimeError(
                        f"Missing {key}"
                    )

            self.validate_path(
                args["path"]
            )

        # =============================================
        # generate_modification
        # =============================================

        elif tool == "generate_modification":

            required = [
                "path",
                "goal",
            ]

            for key in required:

                value = args.get(key)

                if value is None or value == "":

                    raise RuntimeError(
                        f"Missing {key}"
                    )

            self.validate_path(
                args["path"]
            )

        # =============================================
        # modify_file
        # =============================================

        elif tool == "modify_file":

            required = [
                "path",
                "goal",
            ]

            for key in required:

                value = args.get(key)

                if value is None or value == "":

                    raise RuntimeError(
                        f"Missing {key}"
                    )

            self.validate_path(
                args["path"]
            )

    def validate_diff_size(
        self,
        diff
    ):

        if diff is None:
            return

        if len(diff) > self.MAX_DIFF_SIZE:

            raise RuntimeError(
                "Diff exceeds safety limit"
            )

    def validate_patch(
        self,
        patch
    ):

        if not patch:

            raise RuntimeError(
                "Empty patch"
            )

        if len(patch) > self.MAX_PATCH_SIZE:

            raise RuntimeError(
                "Patch too large"
            )

    def validate_path(
        self,
        path
    ):

        if not path:

            raise RuntimeError(
                "Path missing"
            )

        try:

            Path(path)

        except Exception as exc:

            raise RuntimeError(
                f"Invalid path: {path}"
            ) from exc
```


====================================================================================================
PATH: export_agent_single_file.py
====================================================================================================

```python
# export_agent_single_file.py

from pathlib import Path


SOURCE_FOLDER = "."

OUTPUT_FILE = "agent_dump.md"


IGNORE_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".cache",
    "logs",
    "tmp"
}

IGNORE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".pkl",
    ".faiss",
    ".bin",
    ".db"
}


EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".java": "java",
    ".json": "json",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown"
}


def should_ignore(path):

    # prevent recursive self-inclusion
    if path.name == OUTPUT_FILE:
        return True

    for part in path.parts:

        if part in IGNORE_DIRS:
            return True

    if path.suffix.lower() in IGNORE_EXTENSIONS:
        return True

    return False


def get_language(path):

    return EXTENSION_LANGUAGE_MAP.get(
        path.suffix.lower(),
        ""
    )


def export_to_single_file():

    source = Path(SOURCE_FOLDER).resolve()

    output = Path(OUTPUT_FILE).resolve()

    if not source.exists():

        print(
            f"Source folder not found: {source}"
        )

        return

    files_written = 0

    with open(output, "w", encoding="utf-8") as out:

        out.write(
            "# AGENT REPOSITORY EXPORT\n\n"
        )

        for file in sorted(source.rglob("*")):

            if file.is_dir():
                continue

            if should_ignore(file):
                continue

            relative_path = file.relative_to(source)

            try:

                content = file.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

            except Exception as e:

                print(
                    f"Skipped: "
                    f"{relative_path} ({e})"
                )

                continue

            language = get_language(file)

            separator = "=" * 100

            out.write(
                f"\n{separator}\n"
            )

            out.write(
                f"PATH: {relative_path}\n"
            )

            out.write(
                f"{separator}\n\n"
            )

            out.write(
                f"```{language}\n"
            )

            out.write(content)

            out.write("\n```\n\n")

            files_written += 1

            print(
                f"Added: {relative_path}"
            )

    print("\n================================")

    print(
        "Export completed"
    )

    print(
        f"Files added: {files_written}"
    )

    print(
        f"Output file: {output}"
    )

    print("================================")


if __name__ == "__main__":

    export_to_single_file()
```


====================================================================================================
PATH: llm\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: llm\modification_engine.py
====================================================================================================

```python
# llm/modification_engine.py

import json

from llm.ollama_client import (
    OllamaClient
)


class ModificationEngine:

    def __init__(
        self,
        llm=None
    ):

        self.llm = llm or OllamaClient()

    # =====================================================
    # MODIFY FILE
    # =====================================================

    def modify_file(
       self,
       goal,
       file_path,
       original_content,
       retrieved_context=None,
       execution_context=None,
       architecture_notes=None,
    ):

        prompt = self.build_prompt(
            goal=goal,
            file_path=file_path,
            original_content=original_content,
            retrieved_context=retrieved_context or [],
            execution_context=execution_context or "",
            architecture_notes=architecture_notes or []
        )

        response = self.llm.chat([

            {
                "role": "system",
                "content":
                    self.system_prompt()
            },

            {
                "role": "user",
                "content": prompt
            }
        ])

        return self.extract_code(
            response
        )

    # =====================================================
    # SYSTEM
    # =====================================================

    def system_prompt(self):

        return """
You are a repository-aware software engineer.

Rules:

- preserve architecture
- keep minimal diffs
- avoid unrelated changes
- preserve imports unless necessary
- return ONLY final file content

Do not explain.

Return code only.
"""

    # =====================================================
    # PROMPT
    # =====================================================

    def build_prompt(
        self,
        goal,
        file_path,
        original_content,
        retrieved_context,
        execution_context,
        architecture_notes
    ):

        return f"""
TASK

{goal}

FILE

{file_path}

EXECUTION CONTEXT

{json.dumps(
    execution_context,
    indent=2
)}

ARCHITECTURE NOTES

{json.dumps(
    architecture_notes,
    indent=2
)}

RELATED CONTEXT

{json.dumps(
    retrieved_context,
    indent=2
)}

ORIGINAL FILE

{original_content}

OUTPUT

Return the fully modified file.
Do not explain.
Return code only.
"""

    # =====================================================
    # CLEAN RESPONSE
    # =====================================================

    def extract_code(
        self,
        response
    ):

        response = response.strip()

        if response.startswith("```"):

            lines = response.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].startswith(
                "```"
            ):
                lines = lines[:-1]

            response = "\n".join(lines)

        return response
```


====================================================================================================
PATH: llm\ollama_client.py
====================================================================================================

```python
# llm/ollama_client.py

import requests

from requests.exceptions import (
    ConnectionError,
    Timeout,
    RequestException
)


class OllamaClient:

    DEFAULT_TIMEOUT = 120

    def __init__(
        self,
        model="qwen2.5-coder:7b",
        host="http://localhost:11434"
    ):

        self.model = model

        self.host = host.rstrip("/")

    def chat(
        self,
        messages
    ):

        try:

            response = requests.post(

                f"{self.host}/api/chat",

                json={

                    "model":
                        self.model,

                    "messages":
                        messages,

                    "stream":
                        False
                },

                timeout=self.DEFAULT_TIMEOUT
            )

            response.raise_for_status()

        except ConnectionError as exc:

            raise RuntimeError(
                "Unable to connect to Ollama. "
                "Ensure the Ollama server is running."
            ) from exc

        except Timeout as exc:

            raise RuntimeError(
                f"Ollama request exceeded "
                f"{self.DEFAULT_TIMEOUT} seconds."
            ) from exc

        except RequestException as exc:

            raise RuntimeError(
                f"Ollama request failed: {exc}"
            ) from exc

        #
        # JSON parsing
        #

        try:

            data = response.json()

        except ValueError as exc:

            raise RuntimeError(
                "Ollama returned invalid JSON."
            ) from exc

        #
        # Response validation
        #

        message = data.get(
            "message"
        )

        if not isinstance(
            message,
            dict
        ):

            raise RuntimeError(
                "Ollama response missing "
                "'message' object."
            )

        content = message.get(
            "content"
        )

        if content is None:

            raise RuntimeError(
                "Ollama response missing "
                "'content'."
            )

        return str(content)

    # =====================================================
    # HEALTH CHECK
    # =====================================================

    def ping(
        self
    ):

        try:

            response = requests.get(

                f"{self.host}/api/tags",

                timeout=10
            )

            return (
                response.status_code == 200
            )

        except Exception:

            return False
```


====================================================================================================
PATH: logger.py
====================================================================================================

```python
# logger.py

from pathlib import Path
from datetime import datetime


class Logger:

    def __init__(self, log_file=".agent/logs/agent.log"):

        self.log_path = Path(log_file)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message):

        timestamp = datetime.utcnow().isoformat()

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
```


====================================================================================================
PATH: main.py
====================================================================================================

```python
from runtime.runtime import Runtime


def main():
    Runtime().start()


if __name__ == "__main__":
    main()
```


====================================================================================================
PATH: memory\__init__.py
====================================================================================================

```python
from memory.memory import Memory
```


====================================================================================================
PATH: memory\execution_history.py
====================================================================================================

```python
# memory/execution_history.py

from dataclasses import dataclass, field

from typing import Dict, Any

from datetime import datetime


@dataclass
class ExecutionRecord:

    action_id: str

    tool: str

    status: str

    started_at: str = field(
        default_factory=lambda:
        datetime.utcnow().isoformat()
    )

    completed_at: str = ""

    duration_seconds: float = 0.0

    retries: int = 0

    success: bool = False

    input_data: Dict[str, Any] = field(
        default_factory=dict
    )

    output_data: Dict[str, Any] = field(
        default_factory=dict
    )

    error: str = ""
```


====================================================================================================
PATH: memory\memory.py
====================================================================================================

```python
# memory/memory.py


class Memory:

    def __init__(self):

        self.messages = []

    def add(
        self,
        role,
        content
    ):

        self.messages.append({

            "role": role,

            "content": content
        })

    def get(self):

        return self.messages
```


====================================================================================================
PATH: memory\memory_limits.py
====================================================================================================

```python
# memory/memory_limits.py

MAX_COMPLETED_STEPS = 100

MAX_FAILED_STEPS = 100

MAX_RETRIEVED_CHUNKS = 80

MAX_TOOL_OUTPUTS = 50

MAX_TEST_FAILURES = 30

MAX_REFLECTIONS = 20

MAX_REPAIR_HISTORY = 30

MAX_COMMAND_HISTORY = 100

MAX_ARCHITECTURE_NOTES = 50

MAX_GENERATED_CODE = 30

MAX_VALIDATION_RESULTS = 50

MAX_EXECUTION_HISTORY = 200

MAX_MODIFICATION_TARGETS = 100
```


====================================================================================================
PATH: memory\persistence.py
====================================================================================================

```python
# memory/persistence.py

import json
import shutil
import tempfile

from pathlib import Path

from dataclasses import (
    asdict
)

from memory.task_state import (
    TaskState
)

from memory.runtime_memory import (
    RuntimeMemory
)


class StatePersistence:

    VERSION = 1

    def __init__(
        self,
        tasks_dir="tasks"
    ):

        self.tasks_dir = Path(
            tasks_dir
        )

        self.tasks_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    # =====================================================
    # PATHS
    # =====================================================

    def get_task_path(
        self,
        task_id
    ):

        return (
            self.tasks_dir /
            f"{task_id}.json"
        )

    # =====================================================
    # SAVE
    # =====================================================

    def save(
        self,
        state: TaskState,
        task_id: str
    ):

        path = self.get_task_path(
            task_id
        )

        backup_path = path.with_suffix(
            ".backup.json"
        )

        payload = asdict(state)

        payload["_version"] = (
            self.VERSION
        )

        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp"
        )

        try:

            with open(
                temp_path,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    payload,
                    f,
                    indent=2,
                    ensure_ascii=False
                )

            if path.exists():

                shutil.copy2(
                    path,
                    backup_path
                )

            shutil.move(
                temp_path,
                path
            )

        finally:

            temp = Path(temp_path)

            if temp.exists():

                temp.unlink(
                    missing_ok=True
                )

    # =====================================================
    # LOAD
    # =====================================================

    def load(
        self,
        task_id: str
    ) -> TaskState:

        path = self.get_task_path(
            task_id
        )

        if not path.exists():

            raise FileNotFoundError(
                f"Task not found: {task_id}"
            )

        try:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

        except Exception:

            backup = path.with_suffix(
                ".backup.json"
            )

            if not backup.exists():

                raise RuntimeError(
                    "State corrupted and "
                    "backup missing."
                )

            with open(
                backup,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

        # =================================================
        # VERSION VALIDATION
        # =================================================

        version = data.pop(
            "_version",
            1
        )

        if version > self.VERSION:

            raise RuntimeError(
                f"Unsupported state version: "
                f"{version}. "
                f"Current version: "
                f"{self.VERSION}"
            )

        # =================================================
        # RUNTIME MEMORY MIGRATION
        # =================================================

        runtime_memory = data.get(
            "runtime_memory"
        )

        #
        # Older persisted states may not contain
        # runtime_memory at all.
        #
        if runtime_memory is None:

            data["runtime_memory"] = (
                RuntimeMemory()
            )

        #
        # Persisted RuntimeMemory dict
        #
        elif isinstance(
            runtime_memory,
            dict
        ):

            try:

                data["runtime_memory"] = (
                    RuntimeMemory(
                        **runtime_memory
                    )
                )

            except TypeError:

                #
                # Schema drift / corrupted state
                #
                data["runtime_memory"] = (
                    RuntimeMemory()
                )

        #
        # Invalid runtime_memory payload
        #
        else:

            data["runtime_memory"] = (
                RuntimeMemory()
            )

        return TaskState(**data)

    # =====================================================
    # EXISTS
    # =====================================================

    def exists(
        self,
        task_id: str
    ):

        return self.get_task_path(
            task_id
        ).exists()

    # =====================================================
    # DELETE
    # =====================================================

    def delete(
        self,
        task_id: str
    ):

        path = self.get_task_path(
            task_id
        )

        if path.exists():

            path.unlink()

    # =====================================================
    # LIST
    # =====================================================

    def list_tasks(self):

        return sorted(

            path.stem

            for path in self.tasks_dir.glob(
                "*.json"
            )

            if not path.name.endswith(
                ".backup.json"
            )
        )
```


====================================================================================================
PATH: memory\runtime_memory.py
====================================================================================================

```python
# memory/runtime_memory.py

from dataclasses import (
    dataclass,
    field
)

from typing import Dict, Any


@dataclass
class RuntimeMemory:

    total_iterations: int = 0

    retrieval_count: int = 0

    modification_count: int = 0

    validation_count: int = 0

    repair_count: int = 0

    tool_call_count: int = 0

    tokens_used: int = 0

    runtime_errors: int = 0

    successful_repairs: int = 0

    failed_repairs: int = 0

    execution_time_seconds: float = 0.0

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )
```


====================================================================================================
PATH: memory\state_manager.py
====================================================================================================

```python
# memory/state_manager.py

from typing import (
    Optional,
    List
)
from pathlib import Path

from memory.task_state import (
    TaskState
)

from memory.persistence import (
    StatePersistence
)

from memory.execution_history import (
    ExecutionRecord
)


class StateManager:

    def __init__(self):

        self.state: Optional[
            TaskState
        ] = None

        self.task_id = None

        self.persistence = (
            StatePersistence()
        )

    # =====================================================
    # TASK
    # =====================================================

    def create_task(
        self,
        goal: str,
        task_id: str
    ) -> TaskState:

        self.task_id = task_id

        self.state = TaskState(
            goal=goal
        )

        self.save_state()

        return self.state

    def load_state(
        self,
        task_id: str
    ) -> TaskState:

        self.state = (
            self.persistence.load(
                task_id
            )
        )

        self.task_id = task_id

        return self.state

    def save_state(self):

        self._ensure_state()

        self.persistence.save(
            self.state,
            self.task_id
        )

    def get_state(self) -> TaskState:

        self._ensure_state()

        return self.state

    def task_exists(
        self,
        task_id: str
    ) -> bool:

        return self.persistence.exists(
            task_id
        )

    # =====================================================
    # PLAN
    # =====================================================

    def set_plan(
        self,
        actions
    ):

        self._ensure_state()

        self.state.current_plan = [

            action.to_dict()

            if hasattr(
                action,
                "to_dict"
            )
            else action

            for action in actions
        ]

        self._touch()

    # =====================================================
    # EXECUTION QUEUE
    # =====================================================

    def push_execution(
        self,
        execution
    ):

        self._ensure_state()

        execution_dict = (

            execution.to_dict()

            if hasattr(
                execution,
                "to_dict"
            )
            else execution
        )

        existing = {

            item["action_id"]

            for item in
            self.state.pending_executions
        }

        if (
            execution_dict["action_id"]
            in existing
        ):
            return

        self.state.pending_executions.append(
            execution_dict
        )

        self.sort_execution_queue()

        self._touch()

    def push_executions(
        self,
        executions
    ):

        for execution in executions:

            self.push_execution(
                execution
            )

    def pop_next_execution(self):

        self._ensure_state()

        if not self.state.pending_executions:

            return None

        execution = (
            self.state.pending_executions.pop(
                0
            )
        )

        self._touch()

        return execution

    def retry_execution(
        self,
        execution
    ):

        self._ensure_state()

        execution["retries"] = (
            execution.get(
                "retries",
                0
            ) + 1
        )

        execution["status"] = (
            "pending"
        )

        self.state.pending_executions.append(
            execution
        )

        self.sort_execution_queue()

        self._touch()

    def get_pending_executions(self):

        self._ensure_state()

        return (
            self.state.pending_executions
        )

    def sort_execution_queue(self):

        self.state.pending_executions.sort(

            key=lambda x: (

                x.get(
                    "priority",
                    999
                ),

                x.get(
                    "retries",
                    0
                )
            )
        )

    # =====================================================
    # TOOL OUTPUTS
    # =====================================================

    def add_tool_output(
        self,
        tool_name,
        output
    ):

        self._ensure_state()

        status = "success"

        if isinstance(
            output,
            dict
        ):

            if (
                output.get("error")
                or output.get(
                    "success"
                ) is False
            ):
                status = "failed"

        self.state.tool_outputs.append({

            "tool":
                tool_name,

            "status":
                status,

            "result":
                output
        })

        self._touch()

    # =====================================================
    # REFLECTIONS
    # =====================================================

    def add_reflection(
        self,
        reflection: str
    ):

        self._ensure_state()

        self.state.reflections.append(
            reflection
        )

        self._touch()

    # =====================================================
    # EXECUTION HISTORY
    # =====================================================

    def add_execution_record(
        self,
        record: ExecutionRecord
    ):

        self._ensure_state()

        self.state.execution_history.append({

            "action_id":
                record.action_id,

            "tool":
                record.tool,

            "status":
                record.status,

            "started_at":
                record.started_at,

            "completed_at":
                record.completed_at,

            "duration_seconds":
                record.duration_seconds,

            "retries":
                record.retries,

            "success":
                record.success,

            "input_data":
                record.input_data,

            "output_data":
                record.output_data,

            "error":
                record.error
        })

        self._touch()

    # =====================================================
    # RETRIEVAL
    # =====================================================

    def add_chunk(
        self,
        chunk
    ):

        self._ensure_state()

        chunk_id = chunk.get(
            "chunk_id"
        )

        existing = {

            c.get(
                "chunk_id"
            )

            for c in
            self.state.retrieved_chunks
        }

        if (
            chunk_id
            and
            chunk_id in existing
        ):
            return

        self.state.retrieved_chunks.append(
            chunk
        )

        #
        # Automatically register
        # retrieved file as a
        # modification candidate.
        #

        path = chunk.get(
            "file"
        )

        if path:

            self.add_modification_target(
                path
            )

        self._touch()

    # =====================================================
    # MODIFICATION TARGETS
    # =====================================================

    def add_modification_target(
        self,
        file_path: str
    ):

        self._ensure_state()

        if not file_path:
            return

        file_path = file_path.strip()

        if not file_path:
            return

        # Normalize paths to prevent duplicate target entry variants
        file_path = str(Path(file_path))

        if (
            file_path
            not in self.state.modification_targets
        ):

            self.state.modification_targets.append(
                file_path
            )

            self._touch()

    def set_modification_targets(
        self,
        files: List[str]
    ):

        self._ensure_state()

        unique = []

        for file_path in files:

            if not file_path:
                continue

            file_path = file_path.strip()

            if not file_path:
                continue

            # Normalize structural paths prior to safety checking
            file_path = str(Path(file_path))

            if (
                file_path
                not in unique
            ):
                unique.append(
                    file_path
                )

        self.state.modification_targets = (
            unique
        )

        self._touch()

    # =====================================================
    # RUNTIME METRICS
    # =====================================================

    def increment_tool_calls(self):

        self._ensure_state()

        self.state.runtime_memory.tool_call_count += 1

        self._touch()

    def increment_repairs(
        self,
        success=False
    ):

        self._ensure_state()

        self.state.runtime_memory.repair_count += 1

        if success:

            self.state.runtime_memory.successful_repairs += 1

        else:

            self.state.runtime_memory.failed_repairs += 1

        self._touch()

    def increment_retrievals(self):

        self._ensure_state()

        self.state.runtime_memory.retrieval_count += 1

        self._touch()

    # =====================================================
    # INTERNALS
    # =====================================================

    def _ensure_state(self):

        if self.state is None:

            raise RuntimeError(
                "TaskState not initialized."
            )

    def _touch(self):

        self.state.touch()

        if self.task_id:

            self.save_state()

    # =====================================================
    # PIPELINE CACHING
    # =====================================================

    def set_last_modification(
        self,
        modification
    ):

        self._ensure_state()

        self.state.metadata[
            "last_modification"
        ] = modification

        self._touch()

    def get_last_modification(self):

        self._ensure_state()

        return self.state.metadata.get(
            "last_modification"
        )

    def set_last_patch(
        self,
        patch
    ):

        self._ensure_state()

        self.state.metadata[
            "last_patch"
        ] = patch

        self._touch()

    def get_last_patch(self):

        self._ensure_state()

        return self.state.metadata.get(
            "last_patch"
        )
```


====================================================================================================
PATH: memory\task_state.py
====================================================================================================

```python
# memory/task_state.py

from dataclasses import (
    dataclass,
    field
)

from typing import (
    List,
    Dict,
    Any,
    Optional
)

from datetime import datetime

from memory.runtime_memory import (
    RuntimeMemory
)

from memory.execution_history import (
    ExecutionRecord
)

from memory.memory_limits import *


@dataclass
class TaskState:

    # =====================================================
    # CORE
    # =====================================================

    goal: str

    status: str = "active"

    session_id: Optional[str] = None

    created_at: str = field(
        default_factory=lambda:
        datetime.utcnow().isoformat()
    )

    updated_at: str = field(
        default_factory=lambda:
        datetime.utcnow().isoformat()
    )

    version: int = 1

    checkpoint_count: int = 0

    # =====================================================
    # EXECUTION
    # =====================================================

    current_step: str = ""

    completed_steps: List[str] = field(
        default_factory=list
    )

    failed_steps: List[str] = field(
        default_factory=list
    )

    pending_executions: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    execution_history: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    # =====================================================
    # PLANNING
    # =====================================================

    current_plan: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    replans: List[str] = field(
        default_factory=list
    )

    reflections: List[str] = field(
        default_factory=list
    )

    # =====================================================
    # REPOSITORY CONTEXT
    # =====================================================

    touched_files: List[str] = field(
        default_factory=list
    )

    modified_files: List[str] = field(
        default_factory=list
    )

    #
    # Files explicitly selected
    # for modification by retrieval,
    # planning or analysis stages.
    #

    modification_targets: List[str] = field(
        default_factory=list
    )

    active_symbols: List[str] = field(
        default_factory=list
    )

    architecture_notes: List[str] = field(
        default_factory=list
    )

    retrieved_chunks: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    # =====================================================
    # EXECUTION OUTPUTS
    # =====================================================

    generated_code: List[
        Dict[str, str]
    ] = field(
        default_factory=list
    )

    tool_outputs: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    command_history: List[str] = field(
        default_factory=list
    )

    validation_results: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    # =====================================================
    # FAILURES / REPAIR
    # =====================================================

    test_failures: List[str] = field(
        default_factory=list
    )

    repair_history: List[
        Dict[str, Any]
    ] = field(
        default_factory=list
    )

    git_diff: str = ""

    # =====================================================
    # RUNTIME MEMORY
    # =====================================================

    runtime_memory: RuntimeMemory = field(
        default_factory=RuntimeMemory
    )

    # =====================================================
    # METADATA
    # =====================================================

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    # TRIMMING
    # =====================================================

    def trim_memory(self):

        self.completed_steps = (
            self.completed_steps[
                -MAX_COMPLETED_STEPS:
            ]
        )

        self.failed_steps = (
            self.failed_steps[
                -MAX_FAILED_STEPS:
            ]
        )

        self.retrieved_chunks = (
            self.retrieved_chunks[
                -MAX_RETRIEVED_CHUNKS:
            ]
        )

        self.tool_outputs = (
            self.tool_outputs[
                -MAX_TOOL_OUTPUTS:
            ]
        )

        self.test_failures = (
            self.test_failures[
                -MAX_TEST_FAILURES:
            ]
        )

        self.reflections = (
            self.reflections[
                -MAX_REFLECTIONS:
            ]
        )

        self.repair_history = (
            self.repair_history[
                -MAX_REPAIR_HISTORY:
            ]
        )

        self.command_history = (
            self.command_history[
                -MAX_COMMAND_HISTORY:
            ]
        )

        self.architecture_notes = (
            self.architecture_notes[
                -MAX_ARCHITECTURE_NOTES:
            ]
        )

        self.generated_code = (
            self.generated_code[
                -MAX_GENERATED_CODE:
            ]
        )

        self.validation_results = (
            self.validation_results[
                -MAX_VALIDATION_RESULTS:
            ]
        )

        self.execution_history = (
            self.execution_history[
                -MAX_EXECUTION_HISTORY:
            ]
        )

        #
        # Prevent unbounded growth
        # of planner targets.
        #

        if 'MAX_MODIFICATION_TARGETS' in globals():

            self.modification_targets = (
                self.modification_targets[
                    -MAX_MODIFICATION_TARGETS:
                ]
            )

    # =====================================================
    # TIMESTAMP
    # =====================================================

    def touch(self):

        self.updated_at = (
            datetime.utcnow().isoformat()
        )

        self.checkpoint_count += 1

        self.trim_memory()
```


====================================================================================================
PATH: planning\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: planning\action_schema.py
====================================================================================================

```python
# planning/action_schema.py

from dataclasses import (
    dataclass,
    field
)

from typing import (
    Dict,
    Any,
    Optional,
    List
)

from uuid import uuid4


@dataclass
class Action:

    # =====================================================
    # CORE
    # =====================================================

    action_type: str

    title: str

    target: Optional[str] = None

    file_path: Optional[str] = None

    reasoning: str = ""

    # =====================================================
    # EXECUTION
    # =====================================================

    priority: int = 1

    status: str = "pending"

    retries: int = 0

    max_retries: int = 3

    blocking: bool = False

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    dependencies: List[str] = field(
        default_factory=list
    )

    # =====================================================
    # METADATA
    # =====================================================

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    estimated_impact: str = "medium"

    action_id: str = field(
        default_factory=lambda: str(uuid4())
    )

    # =====================================================
    # SERIALIZATION
    # =====================================================

    def to_dict(self):

        return {

            "action_id":
                self.action_id,

            "action_type":
                self.action_type,

            "title":
                self.title,

            "target":
                self.target,

            "file_path":
                self.file_path,

            "reasoning":
                self.reasoning,

            "priority":
                self.priority,

            "status":
                self.status,

            "retries":
                self.retries,

            "max_retries":
                self.max_retries,

            "blocking":
                self.blocking,

            "dependencies":
                self.dependencies,

            "metadata":
                self.metadata,

            "estimated_impact":
                self.estimated_impact
        }
```


====================================================================================================
PATH: planning\action_types.py
====================================================================================================

```python
# planning/action_types.py

# =========================================================
# REPOSITORY UNDERSTANDING
# =========================================================

RETRIEVE = "retrieve"

READ_FILE = "read_file"

ANALYZE = "analyze"

SUMMARIZE = "summarize"


# =========================================================
# MODIFICATION
# =========================================================

MODIFICATION_PLANNING = (
    "modification_planning"
)

MODIFY = "modify"

PATCH = "patch"

GENERATE_MODIFICATION = (
    "generate_modification"
)

GENERATE_PATCH = (
    "generate_patch"
)

WRITE_FILE = "write_file"

VALIDATE = "validate"


# =========================================================
# TESTING
# =========================================================

TEST = "test"

RUN_BACKEND_TESTS = (
    "run_backend_tests"
)

RUN_FRONTEND_TESTS = (
    "run_frontend_tests"
)

RUN_FRONTEND_BUILD = (
    "run_frontend_build"
)


# =========================================================
# GIT / SAFETY
# =========================================================

GIT_STATUS = "git_status"

GIT_DIFF = "git_diff"

ROLLBACK = "rollback"

COMMIT = "commit"


# =========================================================
# RECOVERY / REFLECTION
# =========================================================

REPAIR = "repair"

REFLECT = "reflect"

REPLAN = "replan"


# =========================================================
# TASK TYPES
# =========================================================

BUG_FIX = "bug_fix"

FEATURE = "feature"

REFACTOR = "refactor"

ANALYSIS = "analysis"

UNKNOWN = "unknown"
```


====================================================================================================
PATH: planning\planner.py
====================================================================================================

```python
# planning/planner.py

from typing import List

from memory.task_state import (
    TaskState
)

from planning.action_schema import (
    Action
)

from planning.action_types import (
    RETRIEVE,
    ANALYZE,
    MODIFY,
    VALIDATE,
    TEST,
    GIT_DIFF,
    RUN_BACKEND_TESTS,
    RUN_FRONTEND_BUILD,
    MODIFICATION_PLANNING,
    REPAIR,
    REFLECT,
    SUMMARIZE,
    BUG_FIX,
    FEATURE,
    REFACTOR,
    ANALYSIS,
    UNKNOWN
)

class Planner:

    def __init__(self):

        pass

    # =====================================================
    # MAIN ENTRY
    # =====================================================

    def create_plan(
        self,
        state: TaskState
    ) -> List[Action]:

        goal = state.goal.lower()

        task_type = self.classify_task(
            goal
        )

        # =================================================
        # FAILURE-FIRST
        # =================================================

        if (
            state.test_failures
            or state.failed_steps
        ):

            return self.build_repair_plan(
                state
            )

        # =================================================
        # BUG FIX
        # =================================================

        if task_type == BUG_FIX:

            return self.build_bugfix_plan(
                state
            )

        # =================================================
        # FEATURE
        # =================================================

        elif task_type == FEATURE:

            return self.build_feature_plan(
                state
            )

        # =================================================
        # REFACTOR
        # =================================================

        elif task_type == REFACTOR:

            return self.build_refactor_plan(
                state
            )

        # =================================================
        # ANALYSIS
        # =================================================

        elif task_type == ANALYSIS:

            return self.build_analysis_plan(
                state
            )

        # =================================================
        # FALLBACK
        # =================================================

        return self.build_default_plan(
            state
        )

    # =====================================================
    # TASK CLASSIFICATION
    # =====================================================

    def classify_task(
        self,
        goal: str
    ):

        if any(
            word in goal
            for word in [
                "fix",
                "bug",
                "error",
                "issue",
                "broken",
                "failure",
                "crash"
            ]
        ):

            return BUG_FIX

        elif any(
            word in goal
            for word in [
                "add",
                "implement",
                "create",
                "feature",
                "build"
            ]
        ):

            return FEATURE

        elif any(
            word in goal
            for word in [
                "refactor",
                "cleanup",
                "optimize",
                "improve"
            ]
        ):

            return REFACTOR

        elif any(
            word in goal
            for word in [
                "analyze",
                "explain",
                "understand",
                "review"
            ]
        ):

            return ANALYSIS

        return UNKNOWN

    # =====================================================
    # BUG FIX PLAN
    # =====================================================

    def build_bugfix_plan(
        self,
        state: TaskState
    ):

        targets = self.resolve_target_files(
            state
        )

        if not targets:

            return [

                Action(
                    action_type=RETRIEVE,
                    title="Retrieve related code",
                    target=state.goal,
                    reasoning="Find related implementation",
                    priority=1
                ),

                Action(
                    action_type=ANALYZE,
                    title="Analyze root cause",
                    target="root cause",
                    reasoning="Determine affected files",
                    priority=2
                )
            ]

        modify_actions = [
            Action(
                action_type=MODIFY,
                title=f"Modify {path}",
                file_path=path,
                target=state.goal,
                reasoning=(
                    "Apply minimal safe fix"
                ),
                priority=3,
                blocking=True
            )
            for path in targets
        ]

        return [

            Action(
                action_type=RETRIEVE,
                title="Retrieve related code",
                target=state.goal,
                reasoning="Find related implementation",
                priority=1
            ),

            Action(
                action_type=ANALYZE,
                title="Analyze root cause",
                target="root cause",
                reasoning="Understand failure source",
                priority=2
            ),

            *modify_actions,

            Action(
                action_type=VALIDATE,
                title="Validate modifications",
                target="validate code",
                reasoning="Prevent invalid edits",
                priority=4
            ),

            Action(
                action_type=TEST,
                title="Run verification tests",
                target="affected tests",
                reasoning="Ensure fix correctness",
                priority=5
            ),

            Action(
                action_type=GIT_DIFF,
                title="Inspect final diff",
                target="git diff",
                reasoning="Review generated changes",
                priority=6
            )
        ]

    # =====================================================
    # FEATURE PLAN
    # =====================================================

    def build_feature_plan(
        self,
        state: TaskState
    ):

        targets = self.resolve_target_files(
            state
        )

        if not targets:

            return [

                Action(
                    action_type=RETRIEVE,
                    title="Retrieve related code",
                    target=state.goal,
                    reasoning="Find related implementation",
                    priority=1
                ),

                Action(
                    action_type=ANALYZE,
                    title="Analyze root cause",
                    target="root cause",
                    reasoning="Determine affected files",
                    priority=2
                )
            ]

        feature_modifications = [
            Action(
                action_type=MODIFY,
                title=f"Implement feature in {path}",
                file_path=path,
                target=state.goal,
                reasoning="Apply feature changes",
                priority=4,
                blocking=True
            )
            for path in targets
        ]

        return [

            Action(
                action_type=RETRIEVE,
                title="Retrieve architecture",
                target=state.goal,
                reasoning=(
                    "Understand existing patterns"
                ),
                priority=1
            ),

            Action(
                action_type=ANALYZE,
                title="Analyze integration points",
                target="integration points",
                reasoning=(
                    "Find affected modules"
                ),
                priority=2
            ),

            Action(
                action_type=MODIFICATION_PLANNING,
                title="Plan modifications",
                target="implementation strategy",
                reasoning=(
                    "Minimize architectural impact"
                ),
                priority=3
            ),

            *feature_modifications,

            Action(
                action_type=VALIDATE,
                title="Validate integration",
                target="validate feature",
                reasoning=(
                    "Check architecture safety"
                ),
                priority=5
            ),

            Action(
                action_type=RUN_BACKEND_TESTS,
                title="Run backend tests",
                target="backend validation",
                reasoning=(
                    "Verify backend behavior"
                ),
                priority=6
            ),

            Action(
                action_type=RUN_FRONTEND_BUILD,
                title="Run frontend build",
                target="frontend validation",
                reasoning=(
                    "Verify frontend compile"
                ),
                priority=7
            ),

            Action(
                action_type=GIT_DIFF,
                title="Review final diff",
                target="git diff",
                reasoning=(
                    "Inspect overall changes"
                ),
                priority=8
            )
        ]

    # =====================================================
    # REFACTOR PLAN
    # =====================================================

    def build_refactor_plan(
        self,
        state: TaskState
    ):

        targets = self.resolve_target_files(
            state
        )

        if not targets:

            return [

                Action(
                    action_type=RETRIEVE,
                    title="Retrieve related code",
                    target=state.goal,
                    reasoning="Find related implementation",
                    priority=1
                ),

                Action(
                    action_type=ANALYZE,
                    title="Analyze root cause",
                    target="root cause",
                    reasoning="Determine affected files",
                    priority=2
                )
            ]

        refactor_modifications = [
            Action(
                action_type=MODIFY,
                title=f"Perform refactor in {path}",
                file_path=path,
                target="safe refactor",
                priority=3,
                blocking=True
            )
            for path in targets
        ]

        return [

            Action(
                action_type=RETRIEVE,
                title="Retrieve impacted code",
                target=state.goal,
                priority=1
            ),

            Action(
                action_type=ANALYZE,
                title="Analyze dependencies",
                target="dependency graph",
                priority=2
            ),

            *refactor_modifications,

            Action(
                action_type=VALIDATE,
                title="Validate refactor",
                target="refactor validation",
                priority=4
            ),

            Action(
                action_type=TEST,
                title="Run regression tests",
                target="regression testing",
                priority=5
            )
        ]

    # =====================================================
    # ANALYSIS PLAN
    # =====================================================

    def build_analysis_plan(
        self,
        state: TaskState
    ):

        return [

            Action(
                action_type=RETRIEVE,
                title="Retrieve related code",
                target=state.goal,
                priority=1
            ),

            Action(
                action_type=ANALYZE,
                title="Analyze architecture",
                target=state.goal,
                priority=2
            ),

            Action(
                action_type=SUMMARIZE,
                title="Summarize findings",
                target="analysis summary",
                priority=3
            )
        ]

    # =====================================================
    # REPAIR PLAN
    # =====================================================

    def build_repair_plan(
        self,
        state: TaskState
    ):

        targets = self.resolve_target_files(
        state
    )

        return [

            Action(
                action_type=ANALYZE,
                title="Analyze failures",
                target="failure analysis",
                reasoning=(
                    "Determine failure root cause"
                ),
                priority=1
            ),

            Action(
                action_type=REPAIR,
                title="Repair failing code",
                target="repair implementation",
                reasoning=(
                    "Attempt autonomous repair"
                ),
                priority=2,

                metadata={
                 "targets": targets
     }
            ),

            Action(
                action_type=VALIDATE,
                title="Validate repairs",
                target="repair validation",
                reasoning=(
                    "Ensure repair safety"
                ),
                priority=3
            ),

            Action(
                action_type=TEST,
                title="Re-run tests",
                target="verification tests",
                reasoning=(
                    "Verify repair success"
                ),
                priority=4
            ),

            Action(
                action_type=REFLECT,
                title="Reflect on failures",
                target="reflection",
                reasoning=(
                    "Capture repair learnings"
                ),
                priority=5
            )
        ]

    # =====================================================
    # DEFAULT PLAN
    # =====================================================

    def build_default_plan(
        self,
        state: TaskState
    ):

        return [

            Action(
                action_type=RETRIEVE,
                title="Retrieve related code",
                target=state.goal,
                priority=1
            ),

            Action(
                action_type=ANALYZE,
                title="Understand repository context",
                target=state.goal,
                priority=2
            )
        ]

    # =====================================================
    # TARGET RESOLUTION
    # =====================================================

    def resolve_target_files(
        self,
        state: TaskState
    ) -> List[str]:

        #
        # Highest confidence source
        #

        if getattr(
            state,
            "modification_targets",
            None
        ):

            return list(
                dict.fromkeys(
                    state.modification_targets
                )
            )[:5]

        #
        # Fallback to retrieved chunks
        #

        files = []

        for chunk in getattr(
            state,
            "retrieved_chunks",
            []
        ):

            path = chunk.get("file")

            if (
                path
                and path not in files
            ):
                files.append(path)

        if files:

            return files[:5]

        #
        # Last resort:
        # use repository root context
        #

        return []
```


====================================================================================================
PATH: prompts\system_prompt.txt
====================================================================================================

```
Use this as your final production-ready `system_prompt.txt`.

It combines:

* your repo awareness
* your HRMS architecture rules
* robust JSON enforcement
* safer editing workflow
* better agent behavior
* patch-first editing strategy

This is ready to paste directly.

```text
You are an autonomous coding agent working inside the HRMS repository.

Your job is to make small, correct, repo-aware code changes.

IMPORTANT:
- Read files before editing them.
- Understand surrounding patterns before changing code.
- Prefer existing architecture and conventions over inventing new abstractions.
- Keep changes minimal and scoped.

Repository context:
- Backend: Java 21, Spring Boot, Maven, PostgreSQL, Flyway, Keycloak JWT auth.
- Frontend: React, TypeScript, Vite, Tailwind, TanStack Query, React Router.
- Product direction:
  - Build horizontally and vertically.
  - First create usable list/search/detail/create/edit/delete flows across modules.
  - Then improve UX and polish.

==================================================
AVAILABLE TOOLS
==================================================

1. list_files
2. search_code
3. read_file
4. propose_write
5. apply_write

==================================================
TOOL RESPONSE FORMAT
==================================================

When using tools:
- Respond ONLY with valid raw JSON.
- Never explain tool calls.
- Never use markdown.
- Never wrap JSON in code fences.
- Never output commentary before or after JSON.

Valid schema:

{
  "action": "tool_name",
  "params": {}
}

==================================================
TOOL EXAMPLES
==================================================

{
  "action": "search_code",
  "params": {
    "keyword": "EmployeeController"
  }
}

{
  "action": "read_file",
  "params": {
    "path": "frontend/src/pages/employees/index.tsx"
  }
}

{
  "action": "propose_write",
  "params": {
    "path": "frontend/src/pages/employees/index.tsx",
    "content": "updated file content"
  }
}

{
  "action": "apply_write",
  "params": {
    "path": "frontend/src/pages/employees/index.tsx",
    "content": "final approved file content"
  }
}

==================================================
EDITING WORKFLOW
==================================================

ALWAYS follow this order:

1. search_code
2. read_file
3. analyze surrounding patterns
4. propose_write
5. apply_write

Never skip directly to apply_write unless explicitly instructed.

Use propose_write first so diffs can be reviewed safely.

==================================================
EDITING RULES
==================================================

- Keep changes scoped to the request.
- Prefer minimal edits over large rewrites.
- Preserve existing architecture and naming conventions.
- Reuse existing services, hooks, DTOs, utilities, layouts, and patterns.
- Do not introduce unnecessary abstractions.
- Avoid duplicate logic.

Never edit:
- node_modules
- dist
- build
- target
- .git
- __pycache__
- generated files

Backend rules:
- Never modify committed Flyway migrations.
- Create new migrations for schema changes.
- Preserve RBAC and Keycloak auth behavior.
- Add/update focused tests if backend behavior changes.

Frontend rules:
- Prefer dense operational enterprise UI.
- Avoid excessive whitespace or marketing layouts.
- Reuse existing tables/forms/components where possible.
- Preserve route structure and role-aware UI behavior.

Safety rules:
- Never overwrite unrelated user changes.
- Never remove code unless required.
- Never fabricate files or imports without checking the repo first.
- Always inspect nearby files before implementing patterns.

==================================================
DECISION MAKING
==================================================

Before editing:
- Read related files.
- Inspect existing implementations.
- Follow existing repo conventions.

If uncertain:
- Search for similar implementations first.

If a task is large:
- Break it into smaller safe edits.

==================================================
FINAL RESPONSE RULES
==================================================

When all work is complete:
- Stop using JSON.
- Respond normally in conversational text.
- Summarize:
  - what changed
  - files modified
  - important implementation details
  - verification/tests still needed

Do not invent test results.

==================================================
IMPORTANT
==================================================

Tool calls MUST always be valid JSON.

Bad example:
Sure, I will read the file first.

{
  "action": "read_file"
}

Good example:
{
  "action": "read_file",
  "params": {
    "path": "backend/src/main/java/com/hrms/employee/EmployeeController.java"
  }
}
```

```


====================================================================================================
PATH: reflection\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: reflection\critic.py
====================================================================================================

```python
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
```


====================================================================================================
PATH: reflection\repair_engine.py
====================================================================================================

```python
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
```


====================================================================================================
PATH: reflection\replanner.py
====================================================================================================

```python
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
        state
    ):

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

        return self.planner.create_plan(
            state
        )

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
```


====================================================================================================
PATH: repository\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: repository\diff_manager.py
====================================================================================================

```python
# repository/diff_manager.py
import difflib


class DiffManager:

    def generate_diff(
        self,
        old_content,
        new_content,
        path="file"
    ):

        diff = difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"{path}_old",
            tofile=f"{path}_new",
            lineterm=""
        )

        return "\n".join(diff)
```


====================================================================================================
PATH: repository\file_manager.py
====================================================================================================

```python
# repository/file_manager.py

from pathlib import Path
import shutil


class FileManager:

    IGNORE_DIRS = {
        ".git",
        "__pycache__",
        "node_modules",
        ".agent",
        "tmp"
    }

    def __init__(
        self,
        root="."
    ):

        self.root = Path(
            root
        ).resolve()

    # =====================================================
    # PATH RESOLUTION
    # =====================================================

    def resolve_path(
        self,
        path
    ):

        target = (
            self.root / path
        ).resolve()

        #
        # CRITICAL SECURITY FIX
        #
        # Prevent escaping repository root:
        #
        # ../../secret.txt
        #
        try:

            target.relative_to(
                self.root
            )

        except ValueError:

            raise ValueError(
                "Path outside repository"
            )

        for part in target.parts:

            if part in self.IGNORE_DIRS:

                raise ValueError(
                    f"Ignored path: {path}"
                )

        return target

    # =====================================================
    # READ
    # =====================================================

    def read_file(
        self,
        path,
        start=None,
        end=None
    ):

        target = self.resolve_path(
            path
        )

        if not target.exists():

            raise FileNotFoundError(
                path
            )

        content = target.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        lines = content.splitlines()

        if (
            start is not None
            and end is not None
        ):

            sliced = lines[
                start:end
            ]

            return "\n".join(
                sliced
            )

        return content

    # =====================================================
    # WRITE
    # =====================================================

    def write_file(
        self,
        path,
        content,
        backup=True
    ):

        target = self.resolve_path(
            path
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if (
            backup
            and target.exists()
        ):

            backup_path = (
                target.with_suffix(
                    target.suffix
                    + ".bak"
                )
            )

            shutil.copy2(
                target,
                backup_path
            )

        target.write_text(
            content,
            encoding="utf-8"
        )

    # =====================================================
    # TEMP WRITE
    # =====================================================

    def temp_write(
        self,
        path,
        content
    ):

        temp_dir = (
            self.root
            / ".agent"
            / "tmp"
        )

        temp_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        temp_path = (
            temp_dir / path
        ).resolve()

        #
        # SECURITY FIX
        # Prevent escaping temp folder
        #
        try:

            temp_path.relative_to(
                temp_dir.resolve()
            )

        except ValueError:

            raise ValueError(
                "Path outside temp directory"
            )

        temp_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        temp_path.write_text(
            content,
            encoding="utf-8"
        )

    # =====================================================
    # LIST FILES
    # =====================================================

    def list_files(
        self,
        root="."
    ):

        base = self.resolve_path(
            root
        )

        files = []

        for file in base.rglob("*"):

            if not file.is_file():
                continue

            if any(
                ignored in file.parts
                for ignored in self.IGNORE_DIRS
            ):
                continue

            files.append(

                str(
                    file.relative_to(
                        self.root
                    )
                )
            )

        return files

    # =====================================================
    # SEARCH
    # =====================================================

    def search_code(
        self,
        keyword
    ):

        matches = []

        keyword = str(
            keyword
        ).lower()

        for file in self.list_files():

            try:

                content = self.read_file(
                    file
                )

                if keyword in content.lower():

                    matches.append(
                        file
                    )

            except Exception:

                pass

        return matches
```


====================================================================================================
PATH: repository\git_manager.py
====================================================================================================

```python
# repository/git_manager.py

import subprocess
from pathlib import Path
from typing import Optional


class GitManager:

    def __init__(
        self,
        root="."
    ):

        self.root = Path(root)

    # =====================================================
    # STATUS
    # =====================================================

    def status(self):

        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        return result.stdout

    # =====================================================
    # DIFF
    # =====================================================

    def diff(self):

        result = subprocess.run(
            ["git", "diff"],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        return result.stdout

    # =====================================================
    # CURRENT BRANCH
    # =====================================================

    def current_branch(self):

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        return result.stdout.strip()

    # =====================================================
    # LAST COMMIT
    # =====================================================

    def last_commit(self):

        result = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        return result.stdout.strip()

    # =====================================================
    # CHECKPOINT
    # =====================================================

    def create_checkpoint(
        self,
        message: str = "agent checkpoint"
    ) -> Optional[str]:
        """
        Creates a lightweight recovery point before modifications.
        Returns the commit hash string if successful, or None.
        """
        try:

            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.root,
                check=False
            )

            result = subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    message
                ],
                cwd=self.root,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return None

            return self.last_commit()

        except Exception:
            return None

    # =====================================================
    # COMMIT
    # =====================================================

    def commit(
        self,
        message: str
    ) -> bool:
        """
        Stages all untracked/modified files and runs a git commit.
        """
        try:

            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.root,
                check=True
            )

            result = subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    message
                ],
                cwd=self.root,
                capture_output=True,
                text=True
            )

            return result.returncode == 0

        except Exception:
            return False

    # =====================================================
    # ROLLBACK FILE
    # =====================================================

    def rollback_file(
        self,
        file_path: str
    ) -> bool:
        """
        Reverts modifications to a single specified target file.
        """
        try:

            subprocess.run(
                [
                    "git",
                    "restore",
                    file_path
                ],
                cwd=self.root,
                check=True
            )

            return True

        except Exception:
            return False

    # =====================================================
    # ROLLBACK TO COMMIT
    # =====================================================

    def rollback_to_commit(
        self,
        commit_hash: str
    ) -> bool:
        """
        Performs a full hard reset to a specific previous commit anchor.
        """
        try:

            subprocess.run(
                [
                    "git",
                    "reset",
                    "--hard",
                    commit_hash
                ],
                cwd=self.root,
                check=True
            )

            return True

        except Exception:
            return False
```


====================================================================================================
PATH: repository\patch_generator.py
====================================================================================================

```python
# repository/patch_generator.py

from difflib import unified_diff


class PatchGenerator:

    def generate(
        self,
        original_content: str,
        modified_content: str,
        path: str
    ) -> str:

        diff = unified_diff(
            original_content.splitlines(),
            modified_content.splitlines(),
            fromfile=path,
            tofile=path,
            lineterm=""
        )

        return "\n".join(diff)
```


====================================================================================================
PATH: repository\patch_manager.py
====================================================================================================

```python
# patch_manager.py

import subprocess
from pathlib import Path
import tempfile


class PatchManager:

    def __init__(self, root="."):

        self.root = Path(root)

    def apply_patch(self, patch_text):

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".patch",
            delete=False,
            encoding="utf-8"
        ) as f:

            f.write(patch_text)

            patch_file = f.name

        result = subprocess.run(
            ["git", "apply", patch_file],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:

            return {
                "success": False,
                "error": result.stderr
            }

        return {
            "success": True
        }
```


====================================================================================================
PATH: repository\repo_context.py
====================================================================================================

```python
# repository/repo_context.py
from pathlib import Path


class RepoContext:

    IMPORTANT_FILES = [
        "pom.xml",
        "package.json",
        "README.md"
    ]

    IGNORE_DIRS = {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build"
    }

    IGNORE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".exe",
        ".lock"
    }

    def __init__(self, root="."):

        self.root = Path(root)

    def summarize(self, files):

        important = []

        for file in files:

            # Ignore unwanted folders
            if any(ignore in file for ignore in self.IGNORE_DIRS):
                continue

            # Ignore unwanted file types
            if any(file.endswith(ext) for ext in self.IGNORE_EXTENSIONS):
                continue

            important.append(file)

        important.sort()

        return "\n".join(important[:200])

    def build_summary(self):

        summary = []

        for file in self.IMPORTANT_FILES:

            path = self.root / file

            if path.exists():

                content = path.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                summary.append(
                    f"\nFILE: {file}\n"
                )

                summary.append(
                    content[:3000]
                )

        return "\n".join(summary)
```


====================================================================================================
PATH: repository\write_manager.py
====================================================================================================

```python
# repository/write_manager.py

from pathlib import Path
import shutil


class WriteManager:

    def __init__(self, root="."):

        self.root = Path(root).resolve()

    def write_file(
        self,
        path: str,
        content: str,
        backup=True
    ):

        target = (
            self.root / path
        ).resolve()

        try:
            target.relative_to(
                self.root
            )

        except ValueError:

            raise RuntimeError(
                f"Illegal path: {path}"
            )

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if backup and target.exists():

            backup_path = (
                target.with_suffix(
                    target.suffix + ".bak"
                )
            )

            shutil.copy2(
                target,
                backup_path
            )

        target.write_text(
            content,
            encoding="utf-8"
        )

        return {
            "success": True,
            "path": path
        }
```


====================================================================================================
PATH: retrieval\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: retrieval\chunker\__init__.py
====================================================================================================

```python
from retrieval.chunker.repo_chunker import (
    RepoChunker
)

from retrieval.chunker.python_chunker import (
    PythonChunker
)

from retrieval.chunker.generic_chunker import (
    GenericChunker
)

```


====================================================================================================
PATH: retrieval\chunker\chunk_utils.py
====================================================================================================

```python
# retrieval/chunker/chunk_utils.py

IGNORE_DIRS = {

    ".git",

    "__pycache__",

    "node_modules",

    "venv",

    ".venv",

    "dist",

    "build",

    "target",

    ".pytest_cache",

    ".mypy_cache",

    ".cache"
}

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".env",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".md"
}

MAX_FILE_SIZE_MB = 2

```


====================================================================================================
PATH: retrieval\chunker\generic_chunker.py
====================================================================================================

```python
# retrieval/chunker/generic_chunker.py

import re
from pathlib import Path


class GenericChunker:

    def __init__(self):
        self.max_chunk_lines = 80
        self.chunk_overlap = 15

        # Regex patterns for various file types
        self.java_import_pattern = re.compile(r'^\s*import\s+([\w\.\*]+)\s*;')
        self.js_ts_import_pattern = re.compile(r'^\s*import\s+.*?from\s+[\'"]([^\'"]+)[\'"]')
        self.require_import_pattern = re.compile(r'(?:const|let|var)\s+.*?\s*=\s*require\([\'"]([^\'"]+)[\'"]\)')

        # Symbol detection patterns
        # Java patterns
        self.java_class_pattern = re.compile(r'(?:public|protected|private|static|\s)+class\s+(\w+)')
        self.java_interface_pattern = re.compile(r'(?:public|protected|private|\s)+interface\s+(\w+)')
        self.java_method_pattern = re.compile(r'(?:public|protected|private|static|\s)+(?:[\w<>\[\]\?]+)\s+(\w+)\s*\(')

        # JS / TS / TSX / JSX patterns
        self.js_class_pattern = re.compile(r'class\s+(\w+)')
        self.js_function_pattern = re.compile(r'function\s+(\w+)')
        self.js_arrow_fn_pattern = re.compile(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:\([^\)]*\)|[^=]+)\s*=>')
        self.js_export_default_pattern = re.compile(r'export\s+default\s+function\s+(\w+)?')
        self.js_export_const_pattern = re.compile(r'export\s+const\s+(\w+)')

    # =====================================================
    # MAIN ENTRY
    # =====================================================

    def chunk_file(self, file_path):
        path = Path(file_path)
        suffix = path.suffix.lower()

        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[Generic Chunker Error] {file_path}: {e}")
            return []

        lines = source.splitlines()
        if not lines:
            return []

        # 1. Extract Imports
        imports = self.extract_imports(lines, suffix)

        # 2. Extract Docstrings / Block Comments
        docstrings = self.extract_block_comments(source)

        # 3. Slide over file lines to build chunks
        chunks = []
        total_lines = len(lines)
        start = 0
        chunk_idx = 0

        # Precompute total chunks estimate
        total_chunks_est = max(1, (total_lines - self.chunk_overlap) // (self.max_chunk_lines - self.chunk_overlap) + 1)

        while start < total_lines:
            end = min(start + self.max_chunk_lines, total_lines)
            chunk_lines = lines[start:end]
            chunk_code = "\n".join(chunk_lines)

            # Find matching symbols and docstrings inside this range
            symbol_name, symbol_type = self.detect_symbol(chunk_lines, suffix, path.stem)
            docstring = self.find_relevant_docstring(start + 1, end, docstrings)

            # Define default fallback types based on file type
            if not symbol_type:
                if suffix in {".json", ".yaml", ".yml", ".xml", ".ini", ".env"}:
                    symbol_type = "ConfigBlock"
                elif suffix in {".css", ".scss", ".less"}:
                    symbol_type = "Stylesheet"
                elif suffix == ".md":
                    symbol_type = "Markdown"
                else:
                    symbol_type = "CodeBlock"

            # Create metadata
            chunk_id = f"{path}:{symbol_name or 'chunk'}:{start + 1}"
            metadata = {
                "chunk_id": chunk_id,
                "name": symbol_name or path.name,
                "type": symbol_type,
                "file": str(path),
                "start_line": start + 1,
                "end_line": end,
                "parent": None,
                "docstring": docstring,
                "imports": imports,
                "chunk_index": chunk_idx,
                "total_chunks": total_chunks_est,
                "code": chunk_code
            }

            chunks.append(metadata)
            chunk_idx += 1

            # Advance sliding window
            if end >= total_lines:
                break
            start += (self.max_chunk_lines - self.chunk_overlap)

        # Correct the actual total chunks in metadata
        for chunk in chunks:
            chunk["total_chunks"] = len(chunks)

        return chunks

    # =====================================================
    # IMPORT EXTRACTION
    # =====================================================

    def extract_imports(self, lines, suffix):
        imports = []
        # We only scan the first 100 lines for imports to save time
        scan_limit = min(100, len(lines))

        for i in range(scan_limit):
            line = lines[i]
            if suffix == ".java":
                match = self.java_import_pattern.match(line)
                if match:
                    imports.append(match.group(1))
            elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
                match = self.js_ts_import_pattern.match(line)
                if match:
                    imports.append(match.group(1))
                else:
                    match = self.require_import_pattern.search(line)
                    if match:
                        imports.append(match.group(1))
        return list(set(imports))

    # =====================================================
    # COMMENT / DOCSTRING EXTRACTION
    # =====================================================

    def extract_block_comments(self, source):
        # Extract JSDoc / JavaDoc blocks with their line numbers
        docstrings = []
        # Find all /** ... */ or /* ... */ blocks
        pattern = re.compile(r'/\*\*([\s\S]*?)\*/|/\*([\s\S]*?)\*/')
        
        for match in pattern.finditer(source):
            comment_text = match.group(1) or match.group(2)
            comment_text = comment_text.strip()
            
            # Find the starting line of this comment
            start_pos = match.start()
            start_line = source[:start_pos].count('\n') + 1
            end_line = start_line + comment_text.count('\n')
            
            docstrings.append({
                "start": start_line,
                "end": end_line,
                "text": comment_text
            })
        return docstrings

    def find_relevant_docstring(self, chunk_start, chunk_end, docstrings):
        # Return the docstring that overlaps with or directly precedes the chunk
        best_doc = ""
        for doc in docstrings:
            # If the docstring is within the chunk or just above it (up to 5 lines above)
            if (doc["start"] >= chunk_start and doc["start"] <= chunk_end) or \
               (doc["end"] >= chunk_start - 5 and doc["end"] <= chunk_start):
                best_doc = doc["text"]
                break
        return best_doc

    # =====================================================
    # SYMBOL DETECTION
    # =====================================================

    def detect_symbol(self, chunk_lines, suffix, default_name):
        # Detect the first prominent symbol declaration in the chunk lines
        for line in chunk_lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("//") or line_str.startswith("*") or line_str.startswith("/*"):
                continue

            if suffix == ".java":
                match = self.java_class_pattern.search(line)
                if match:
                    return match.group(1), "ClassDef"
                match = self.java_interface_pattern.search(line)
                if match:
                    return match.group(1), "InterfaceDef"
                match = self.java_method_pattern.search(line)
                if match:
                    return match.group(1), "FunctionDef"

            elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
                match = self.js_class_pattern.search(line)
                if match:
                    return match.group(1), "ClassDef"
                match = self.js_export_default_pattern.search(line)
                if match:
                    return match.group(1) or default_name, "FunctionDef"
                match = self.js_function_pattern.search(line)
                if match:
                    return match.group(1), "FunctionDef"
                match = self.js_arrow_fn_pattern.search(line)
                if match:
                    return match.group(1), "FunctionDef"
                match = self.js_export_const_pattern.search(line)
                if match:
                    return match.group(1), "FunctionDef"

        return None, None

```


====================================================================================================
PATH: retrieval\chunker\python_chunker.py
====================================================================================================

```python
# retrieval/chunker/python_chunker.py

import ast

from pathlib import Path


class PythonChunker:

    def __init__(self):

        self.max_chunk_lines = 120

        self.chunk_overlap = 20

    # =====================================================
    # MAIN
    # =====================================================

    def chunk_file(
        self,
        file_path
    ):

        path = Path(file_path)

        try:

            source = path.read_text(
                encoding="utf-8",
                errors="ignore"
            )

        except Exception as e:

            print(
                f"[Chunker Error] "
                f"{file_path}: {e}"
            )

            return []

        try:

            tree = ast.parse(source)

        except SyntaxError:

            return []

        imports = self.extract_imports(
            tree
        )

        lines = source.splitlines()

        chunks = []

        for node in tree.body:

            if isinstance(node, (
                ast.ClassDef,
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )):

                built = self.process_node(

                    node=node,

                    lines=lines,

                    imports=imports,

                    path=path,

                    parent=None
                )

                chunks.extend(built)

        return chunks

    # =====================================================
    # NODE PROCESSING
    # =====================================================

    def process_node(
        self,
        node,
        lines,
        imports,
        path,
        parent
    ):

        chunks = []

        start = node.lineno

        end = node.end_lineno

        node_lines = lines[start - 1:end]

        metadata = {

            "chunk_id":
                f"{path}:{node.name}:{start}",

            "name":
                node.name,

            "type":
                type(node).__name__,

            "file":
                str(path),

            "start_line":
                start,

            "end_line":
                end,

            "parent":
                parent,

            "docstring":
                ast.get_docstring(node) or "",

            "imports":
                imports
        }

        # =============================================
        # SMALL CHUNK
        # =============================================

        if len(node_lines) <= self.max_chunk_lines:

            chunks.append({

                **metadata,

                "chunk_index": 0,

                "total_chunks": 1,

                "code":
                    "\n".join(node_lines)
            })

        # =============================================
        # LARGE CHUNK
        # =============================================

        else:

            split_chunks = self.split_chunk(
                node_lines
            )

            for i, split in enumerate(
                split_chunks
            ):

                chunks.append({

                    **metadata,

                    "chunk_index": i,

                    "total_chunks":
                        len(split_chunks),

                    "code":
                        split
                })

        # =============================================
        # CLASS CHILDREN
        # =============================================

        if isinstance(node, ast.ClassDef):

            for child in node.body:

                if isinstance(child, (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef
                )):

                    child_chunks = (
                        self.process_node(

                            node=child,

                            lines=lines,

                            imports=imports,

                            path=path,

                            parent=node.name
                        )
                    )

                    chunks.extend(
                        child_chunks
                    )

        return chunks

    # =====================================================
    # SPLIT LARGE CHUNKS
    # =====================================================

    def split_chunk(
        self,
        lines
    ):

        chunks = []

        start = 0

        while start < len(lines):

            end = start + self.max_chunk_lines

            piece = lines[start:end]

            chunks.append(
                "\n".join(piece)
            )

            start += (
                self.max_chunk_lines
                - self.chunk_overlap
            )

        return chunks

    # =====================================================
    # IMPORT EXTRACTION
    # =====================================================

    def extract_imports(
        self,
        tree
    ):

        imports = []

        for node in ast.walk(tree):

            if isinstance(node, ast.Import):

                for alias in node.names:

                    imports.append(
                        alias.name
                    )

            elif isinstance(
                node,
                ast.ImportFrom
            ):

                imports.append(
                    node.module or ""
                )

        return imports
```


====================================================================================================
PATH: retrieval\chunker\repo_chunker.py
====================================================================================================

```python
# retrieval/chunker/repo_chunker.py

from collections import Counter
from pathlib import Path

from retrieval.chunker.chunk_utils import (
    IGNORE_DIRS,
    SUPPORTED_EXTENSIONS,
    MAX_FILE_SIZE_MB
)

from retrieval.chunker.python_chunker import (
    PythonChunker
)

from retrieval.chunker.generic_chunker import (
    GenericChunker
)


class RepoChunker:

    def __init__(self):

        self.python_chunker = (
            PythonChunker()
        )

        self.generic_chunker = (
            GenericChunker()
        )

    # =====================================================
    # FILTERS
    # =====================================================

    def should_skip(
        self,
        path
    ):

        if any(
            part in IGNORE_DIRS
            for part in path.parts
        ):

            return True

        try:

            size_mb = (
                path.stat().st_size
                / (1024 * 1024)
            )

            return size_mb > MAX_FILE_SIZE_MB

        except Exception:

            return True

    # =====================================================
    # BUILD
    # =====================================================

    def build_chunks(
        self,
        root="."
    ):

        root = Path(root)

        all_chunks = []
        files_by_ext = Counter()

        print(
            f"[Chunker] Scanning repository: {root.resolve()}"
        )

        # Walk all files under the root directory
        for path in root.rglob("*"):

            if not path.is_file():
                continue

            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                continue

            if self.should_skip(path):
                continue

            try:

                if suffix == ".py":
                    chunks = (
                        self.python_chunker
                        .chunk_file(path)
                    )
                else:
                    chunks = (
                        self.generic_chunker
                        .chunk_file(path)
                    )

                if chunks:
                    all_chunks.extend(chunks)
                    files_by_ext[suffix] += 1

            except Exception as e:

                print(
                    f"[Chunker Error] "
                    f"{path}: {e}"
                )

        print("\n[Chunker] Scan Summary by Extension:")
        for ext, count in sorted(files_by_ext.items()):
            print(f"  {ext}: {count} files")

        print(
            f"[Chunker] Total chunks generated: {len(all_chunks)}\n"
        )

        return all_chunks

```


====================================================================================================
PATH: retrieval\embedding_engine.py
====================================================================================================

```python
from sentence_transformers import SentenceTransformer
import numpy as np
import time


class EmbeddingEngine:

    def __init__(self):

        print("[Embedding] Loading model...")

        start = time.time()

        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

        end = time.time()

        print(
            f"[Embedding] Model loaded "
            f"in {end - start:.2f}s"
        )

    def embed_text(self, text):

        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        return embedding.astype(np.float32)

    def embed_batch(self, texts, batch_size=32):

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True
        )

        return embeddings.astype(np.float32)
```


====================================================================================================
PATH: retrieval\retrieval_pipeline.py
====================================================================================================

```python
# retrieval/retrieval_pipeline.py

from collections import defaultdict


class RetrievalPipeline:

    def __init__(
        self,
        retriever
    ):

        self.retriever = retriever

    # =====================================================
    # MAIN
    # =====================================================

    def retrieve_relevant_chunks(
        self,
        query,
        top_k=8,
        expand_context=True
    ):

        results = self.retriever.search(
            query=query,
            top_k=top_k
        )

        if not results:
            return []

        results = self.deduplicate(
            results
        )

        if expand_context:

            results = self.expand_neighbors(
                results
            )

        results = self.rerank(
            query,
            results
        )

        return results[:top_k]

    # =====================================================
    # DEDUPLICATION
    # =====================================================

    def deduplicate(
        self,
        results
    ):

        seen = set()

        deduped = []

        for item in results:

            chunk = item["chunk"]

            key = chunk.get(
                "chunk_id"
            )

            if key in seen:
                continue

            seen.add(key)

            deduped.append(item)

        return deduped

    # =====================================================
    # CONTEXT EXPANSION
    # =====================================================

    def expand_neighbors(
        self,
        results
    ):

        expanded = []

        lookup = defaultdict(list)

        for chunk in self.retriever.chunks:

            lookup[
                chunk["file"]
            ].append(chunk)

        for item in results:

            expanded.append(item)

            chunk = item["chunk"]

            current_index = chunk.get(
                "chunk_index",
                0
            )

            siblings = lookup[
                chunk["file"]
            ]

            for sibling in siblings:

                sibling_index = sibling.get(
                    "chunk_index",
                    0
                )

                if abs(
                    sibling_index
                    - current_index
                ) <= 1:

                    expanded.append({

                        "score":
                            item["score"] * 0.92,

                        "chunk":
                            sibling
                    })

        return expanded

    # =====================================================
    # RERANK
    # =====================================================

    def rerank(
        self,
        query,
        results
    ):

        query_lower = query.lower()

        for item in results:

            chunk = item["chunk"]

            score = item["score"]

            # =============================================
            # SYMBOL BOOST
            # =============================================

            if query_lower in chunk.get(
                "name",
                ""
            ).lower():

                score += 0.20

            # =============================================
            # FILE BOOST
            # =============================================

            if query_lower in chunk.get(
                "file",
                ""
            ).lower():

                score += 0.15

            # =============================================
            # DOCSTRING BOOST
            # =============================================

            if query_lower in chunk.get(
                "docstring",
                ""
            ).lower():

                score += 0.10

            # =============================================
            # PARENT BOOST
            # =============================================

            if query_lower in str(
                chunk.get("parent", "")
            ).lower():

                score += 0.08

            item["score"] = score

        results.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return results
```


====================================================================================================
PATH: retrieval\retriever.py
====================================================================================================

```python
# retrieval/retriever.py

import os
import time
import pickle
import faiss

from retrieval.chunker import (
    RepoChunker
)

from retrieval.embedding_engine import (
    EmbeddingEngine
)

from retrieval.vector_store import (
    VectorStore
)


INDEX_DIR = ".cache"

INDEX_FILE = os.path.join(
    INDEX_DIR,
    "code_index.faiss"
)

CHUNKS_FILE = os.path.join(
    INDEX_DIR,
    "chunks.pkl"
)


class CodeRetriever:

    def __init__(
        self,
        repo_root="."
    ):

        self.repo_root = repo_root

        os.makedirs(
            INDEX_DIR,
            exist_ok=True
        )

        self.chunker = RepoChunker()

        self.embedding_engine = (
            EmbeddingEngine()
        )

        self.chunks = []

        self.vector_store = None

        print(
            "\n[Retriever] Initializing"
        )

        if self.cache_exists():

            try:

                self.load_cache()

            except Exception as e:

                print(
                    f"[Retriever] "
                    f"Cache load failed: {e}"
                )

                self.build_index()

        else:

            self.build_index()

    # =====================================================
    # CACHE
    # =====================================================

    def cache_exists(self):

        return (

            os.path.exists(INDEX_FILE)

            and

            os.path.exists(CHUNKS_FILE)
        )

    # =====================================================
    # INDEX BUILD
    # =====================================================

    def build_index(self):

        start = time.time()

        print(
            "[Retriever] Building chunks"
        )

        self.chunks = (
            self.chunker.build_chunks(
                self.repo_root
            )
        )

        if not self.chunks:

            raise RuntimeError(
                "No chunks generated."
            )

        texts = [

            self.build_search_text(chunk)

            for chunk in self.chunks
        ]

        print(
            "[Retriever] Embedding chunks"
        )

        embeddings = (
            self.embedding_engine
            .embed_batch(texts)
        )

        dimension = embeddings.shape[1]

        self.vector_store = (
            VectorStore(dimension)
        )

        for embedding, chunk in zip(
            embeddings,
            self.chunks
        ):

            self.vector_store.add(
                embedding,
                chunk
            )

        self.save_cache()

        end = time.time()

        print(
            f"[Retriever] "
            f"Indexed {len(self.chunks)} "
            f"chunks in "
            f"{end - start:.2f}s"
        )

    # =====================================================
    # SEARCH TEXT
    # =====================================================

    def build_search_text(
        self,
        chunk
    ):

        return f"""
SYMBOL:
{chunk.get("name", "")}

TYPE:
{chunk.get("type", "")}

FILE:
{chunk.get("file", "")}

DOCSTRING:
{chunk.get("docstring", "")}

IMPORTS:
{' '.join(chunk.get("imports", []))}

CODE:
{chunk.get("code", "")}
"""

    # =====================================================
    # SAVE CACHE
    # =====================================================

    def save_cache(self):

        faiss.write_index(
            self.vector_store.index,
            INDEX_FILE
        )

        with open(
            CHUNKS_FILE,
            "wb"
        ) as f:

            pickle.dump(
                self.chunks,
                f
            )

        print(
            "[Retriever] Cache saved"
        )

    # =====================================================
    # LOAD CACHE
    # =====================================================

    def load_cache(self):

        index = faiss.read_index(
            INDEX_FILE
        )

        with open(
            CHUNKS_FILE,
            "rb"
        ) as f:

            chunks = pickle.load(f)

        dimension = index.d

        self.vector_store = (
            VectorStore(dimension)
        )

        self.vector_store.index = index

        self.vector_store.chunks = chunks

        self.chunks = chunks

        print(
            f"[Retriever] "
            f"Loaded {len(chunks)} chunks"
        )

    # =====================================================
    # SEARCH
    # =====================================================

    def search(
        self,
        query,
        top_k=10
    ):

        start = time.time()

        embedding = (
            self.embedding_engine
            .embed_text(query)
        )

        results = (
            self.vector_store.search(
                embedding,
                top_k=top_k
            )
        )

        end = time.time()

        print(
            f"[Retriever] Search took "
            f"{end - start:.2f}s"
        )

        return results
```


====================================================================================================
PATH: retrieval\vector_store.py
====================================================================================================

```python
# retrieval/vector_store.py

import faiss
import numpy as np


class VectorStore:

    def __init__(
        self,
        dimension: int
    ):

        self.dimension = dimension

        self.index = faiss.IndexFlatIP(
            dimension
        )

        self.chunks = []

    # =====================================================
    # NORMALIZATION
    # =====================================================

    def normalize(
        self,
        vector
    ):

        norm = np.linalg.norm(vector)

        if norm == 0:
            return vector

        return vector / norm

    # =====================================================
    # ADD
    # =====================================================

    def add(
        self,
        embedding,
        chunk
    ):

        embedding = self.normalize(
            embedding
        )

        embedding = np.array(
            [embedding],
            dtype=np.float32
        )

        self.index.add(embedding)

        self.chunks.append(chunk)

    # =====================================================
    # SEARCH
    # =====================================================

    def search(
        self,
        query_embedding,
        top_k=10,
        min_score=0.20
    ):

        if self.index.ntotal == 0:
            return []

        query_embedding = self.normalize(
            query_embedding
        )

        query_embedding = np.array(
            [query_embedding],
            dtype=np.float32
        )

        top_k = min(
            top_k,
            self.index.ntotal
        )

        scores, indices = self.index.search(
            query_embedding,
            top_k
        )

        results = []

        for score, idx in zip(
            scores[0],
            indices[0]
        ):

            if idx == -1:
                continue

            if score < min_score:
                continue

            results.append({

                "score": float(score),

                "chunk":
                    self.chunks[idx]
            })

        return results

    # =====================================================
    # INFO
    # =====================================================

    def total_vectors(self):

        return self.index.ntotal
```


====================================================================================================
PATH: runtime\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: runtime\execution_engine.py
====================================================================================================

```python
# runtime/execution_engine.py


class ExecutionEngine:

    def __init__(
        self,
        executor,
        state_manager
    ):

        self.executor = executor

        self.state_manager = (
            state_manager
        )

    # =====================================================
    # MAIN
    # =====================================================

    def run(self):
        """
        Execute the next pending action.

        Runtime repeatedly calls this
        until the queue is exhausted.
        """

        pending = (
            self.state_manager
            .get_pending_executions()
        )

        if not pending:
            return None

        execution = pending[0]

        #
        # mark running
        #
        if isinstance(
            execution,
            dict
        ):
            execution["status"] = (
                "running"
            )

        result = (
            self.executor.execute(
                execution
            )
        )

        #
        # remove executed item
        #
        completed = (
            self.state_manager
            .pop_next_execution()
        )

        #
        # update state tracking
        #
        state = (
            self.state_manager
            .get_state()
        )

        action_id = None

        if isinstance(
            completed,
            dict
        ):
            action_id = completed.get(
                "action_id"
            )

        if (
            isinstance(
                result,
                dict
            )
            and result.get(
                "success",
                False
            )
        ):

            if action_id:

                state.completed_steps.append(
                    action_id
                )

        else:

            if action_id:

                state.failed_steps.append(
                    action_id
                )

            #
            # retry if possible
            #
            if (
                completed
                and hasattr(
                    self.state_manager,
                    "retry_execution"
                )
            ):

                retries = completed.get(
                    "retries",
                    0
                )

                max_retries = completed.get(
                    "max_retries",
                    3
                )

                if retries < max_retries:

                    self.state_manager.retry_execution(
                        completed
                    )

        self.state_manager.save_state()

        return result
```


====================================================================================================
PATH: runtime\recovery_loop.py
====================================================================================================

```python
# runtime/recovery_loop.py

from reflection.replanner import (
    Replanner
)

from execution.action_compiler import (
    ActionCompiler
)


class RecoveryLoop:

    def __init__(
        self,
        state_manager
    ):

        self.state_manager = (
            state_manager
        )

        self.replanner = (
            Replanner()
        )

        self.compiler = (
            ActionCompiler()
        )

    # ==========================================
    # MAIN
    # ==========================================

    def run(self):

        state = (
            self.state_manager.get_state()
        )

        new_actions = (
            self.replanner.replan(
                state
            )
        )

        if not new_actions:

            return False

        executions = (
            self.compiler.compile(
                new_actions
            )
        )

        self.state_manager.push_executions(
            executions
        )

        return True
```


====================================================================================================
PATH: runtime\runtime.py
====================================================================================================

```python
# runtime/runtime.py

from uuid import uuid4

from planning.planner import (
    Planner
)

from execution.action_compiler import (
    ActionCompiler
)

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

        self.state_manager = (
            StateManager()
        )

        self.planner = Planner()

        self.compiler = (
            ActionCompiler()
        )

        self.context = (
            ContextAssembler()
        )

        self.prompts = (
            PromptBuilder()
        )

        self.llm = OllamaClient()

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
                self.state_manager
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

        actions = (
            self.planner.create_plan(
                state
            )
        )

        self.state_manager.set_plan(
            actions
        )

        executions = (
            self.compiler.compile(
                actions
            )
        )

        self.state_manager.push_executions(
            executions
        )

        iteration = 0

        while (
            iteration
            < self.MAX_ITERATIONS
        ):

            iteration += 1

            state.runtime_memory.total_iterations += 1

            self.engine.run()

            pending = (
                self.state_manager
                .get_pending_executions()
            )

            if pending:
                continue

            recovered = (
                self.recovery.run()
            )

            if not recovered:
                break

        state.status = "completed"

        self.state_manager.save_state()

        print(
            "\nTask Complete"
        )
```


====================================================================================================
PATH: test_chunker.py
====================================================================================================

```python
from retrieval.chunker.repo_chunker import (
    RepoChunker
)

chunker = RepoChunker()

chunks = chunker.build_chunks(".")

print(f"\nTotal chunks: {len(chunks)}\n")

for chunk in chunks[:5]:

    print("=" * 80)

    print(
        chunk.get(
            "name",
            "NO_NAME"
        )
    )

    print(
        chunk.get(
            "type",
            "NO_TYPE"
        )
    )

    print(
        f"{chunk.get('file')} "
        f"({chunk.get('start_line')}-"
        f"{chunk.get('end_line')})"
    )

    print()

    print(
        chunk.get(
            "code",
            "NO_CODE"
        )[:500]
    )
```


====================================================================================================
PATH: test_retriever.py
====================================================================================================

```python
from retrieval.retriever import (
    CodeRetriever
)

from retrieval.retrieval_pipeline import (
    RetrievalPipeline
)


print("\n[TEST] Starting retriever...\n")

retriever = CodeRetriever(
    repo_root=".."
)

pipeline = RetrievalPipeline(
    retriever
)

print(
    f"\n[TEST] Total indexed vectors: "
    f"{retriever.vector_store.total_vectors()}"
)

print("\n[TEST] Ready for queries\n")


while True:

    try:

        query = input(
            "\nSearch Query > "
        ).strip()

        if not query:
            continue

        if query.lower() in {
            "exit",
            "quit",
            "q"
        }:
            break

        results = pipeline.retrieve_relevant_chunks(
            query=query,
            top_k=8,
            expand_context=True
        )

        print("\nRESULTS\n")

        if not results:

            print("No results found.")
            continue

        for i, item in enumerate(results[:5]):

            chunk = item["chunk"]

            print("=" * 80)

            print(
                f"Result #{i+1}"
            )

            print(
                f"Score: "
                f"{item['score']:.4f}"
            )

            print(
                f"Name: "
                f"{chunk['name']}"
            )

            print(
                f"Type: "
                f"{chunk['type']}"
            )

            print(
                f"File: "
                f"{chunk['file']}"
            )

            print(
                f"Lines: "
                f"{chunk['start_line']}"
                f"-{chunk['end_line']}"
            )

            print(
                f"Chunk: "
                f"{chunk.get('chunk_index', 0)+1}/"
                f"{chunk.get('total_chunks', 1)}"
            )

            if chunk.get("docstring"):

                print(
                    f"Docstring: "
                    f"{chunk['docstring'][:200]}"
                )

            if chunk.get("imports"):

                imports_preview = (
                    ", ".join(
                        chunk["imports"][:5]
                    )
                )

                print(
                    f"Imports: "
                    f"{imports_preview}"
                )

            print("\nCODE\n")

            print(
                chunk['code'][:1200]
            )

            print()

    except KeyboardInterrupt:

        print("\n[TEST] Exiting...")
        break

    except Exception as e:

        print(
            f"\n[ERROR] {e}"
        )
```


====================================================================================================
PATH: testing\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: tools\__init__.py
====================================================================================================

```python

```


====================================================================================================
PATH: tools.py
====================================================================================================

```python
# tools.py

TOOLS = [
    "list_files",
    "search_code",
    "read_file",
    "propose_write",
    "apply_write"
]
```

