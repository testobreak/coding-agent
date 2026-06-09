# execution/execution_state.py
#
# ExecutionState enum representing the lifecycle state machine of the agent.

from enum import Enum

class ExecutionState(Enum):
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
