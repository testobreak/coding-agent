# planning/task_status.py
#
# TaskStatus enum representing state of a TaskNode in the execution DAG.

from enum import Enum

class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
