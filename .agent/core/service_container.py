# core/service_container.py
from typing import Any, Optional

class ServiceContainer:
    """Holds shared infrastructure services only.
    No loops, planning, reflection, or mode-specific runtime loops.
    """
    def __init__(self):
        # Core infrastructure
        self.db = None
        self.retriever = None
        self.model_service = None
        self.llm = None
        self.file_manager = None
        self.context_assembler = None
        self.prompt_builder = None
        self.validator = None
        self.patch_engine = None

        # Mode-specific execution helpers
        self.state_manager = None
        self.executor = None

        # Cursor-specific services
        self.ide_bridge = None
        self.span_locator = None
        self.patch_preview = None

        # Agent-specific services
        self.planner = None
        self.critic = None
        self.replanner = None
