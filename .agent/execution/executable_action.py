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
