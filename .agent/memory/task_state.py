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
    # EXECUTION PLAN DAG
    # =====================================================

    execution_plan: Optional[Dict[str, Any]] = None

    execution_state: str = "PLANNING"

    # =====================================================
    # METADATA
    # =====================================================

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    @property
    def compactor(self):
        if not hasattr(self, "_compactor"):
            from memory.compaction import MemoryCompactor
            self._compactor = MemoryCompactor()
        return self._compactor

    def trim_memory(self):
        # Run automatic memory compaction and DB summarization
        self.compactor.compact(self)

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
