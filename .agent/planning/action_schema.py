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
