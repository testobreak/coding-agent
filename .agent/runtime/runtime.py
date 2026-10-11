# runtime/runtime.py
import os
from core.bootstrap import bootstrap
from core.execution_mode import ExecutionMode
from core.runtime_mode import RuntimeMode

class Runtime:
    """Backward-compatibility layer for legacy Runtime callers.
    Delegates all infrastructure service lookups to the ServiceContainer
    and delegates CLI and goal executions to the proper app runtimes.
    """
    MAX_ITERATIONS = 20

    def __init__(self, services=None):
        if services is not None:
            self._services = services
        else:
            mode_str = os.getenv("AGENT_MODE", "local_cursor").strip().lower()
            mode = ExecutionMode.AGENT if mode_str == "agent" else ExecutionMode.CURSOR
            self._services = bootstrap(mode)

        # Expose mode property mapping to legacy RuntimeMode
        mode_str = os.getenv("AGENT_MODE", "local_cursor").strip().lower()
        if mode_str == "agent":
            self.mode = RuntimeMode.AGENT
        else:
            self.mode = RuntimeMode.LOCAL_CURSOR

    @property
    def model_service(self):
        return self._services.model_service

    @property
    def state_manager(self):
        return self._services.state_manager

    @property
    def llm(self):
        return self._services.llm

    @property
    def context(self):
        return self._services.context_assembler

    @property
    def prompts(self):
        return self._services.prompt_builder

    @property
    def file_manager(self):
        return self._services.file_manager

    @property
    def executor(self):
        return self._services.executor

    @property
    def engine(self):
        return None

    @property
    def recovery(self):
        return None

    def start(self):
        raise RuntimeError(
            "[Runtime] Runtime.start() is legacy. Use CursorServer.start() instead."
        )

    def run_goal(self, goal, on_progress=None):
        from apps.cursor_runtime import CursorRuntime
        cursor_runtime = CursorRuntime(self._services)
        return cursor_runtime.run_goal(goal, on_progress)
