# apps/cursor_runtime.py
import os
import sys
import signal
from core.service_container import ServiceContainer


class CursorRuntime:
    """Manages the event-driven Local Cursor server and handles prompt/patch execution.
    Acts as a router to dispatch requests to the stateless CursorEngine or the
    autonomous stateful AgentEngine.
    """
    def __init__(self, services: ServiceContainer, port: int = 8000):
        self.services = services
        self.port = port

    @property
    def file_manager(self):
        return self.services.file_manager

    @property
    def state_manager(self):
        return self.services.state_manager

    @property
    def model_service(self):
        return self.services.model_service

    @property
    def llm(self):
        return self.services.llm

    @property
    def context(self):
        return self.services.context_assembler

    @property
    def prompts(self):
        return self.services.prompt_builder

    @property
    def executor(self):
        return self.services.executor

    def start(self):
        print(f"[CursorRuntime] Starting HTTP API server on port {self.port}...")
        
        # Wire server runtime dependencies
        from runtime.server import run_server, AgentHTTPHandler
        
        # Inject compatibility runtime into the handler
        from runtime.runtime import Runtime
        compatibility_runtime = Runtime(services=self.services)
        AgentHTTPHandler._runtime = compatibility_runtime
        
        # Graceful shutdown handler
        def _handle_sigint(sig, frame):
            print("\n[CursorRuntime] Exiting cleanly.")
            sys.exit(0)
        signal.signal(signal.SIGINT, _handle_sigint)

        try:
            run_server(port=self.port)
        except SystemExit:
            pass
        except Exception as e:
            print(f"[CursorRuntime] Server encountered fatal error: {e}")
            raise

    def run_goal(self, goal: str, on_progress=None):
        # Resolve active_file and editor_context first
        from context.session_cache import SessionCache
        session_ctx = SessionCache.get_session("default")
        editor_context = getattr(session_ctx, "editor_context", None) if session_ctx else None

        # Resolve routing decision using FastPathRouter
        from runtime.fast_path_router import FastPathRouter

        route_decision = FastPathRouter.route(goal, editor_context)
        execution_mode = route_decision.execution_mode

        # Route to CursorEngine for pure stateless Cursor execution
        from execution.cursor_engine import CursorEngine
        engine = CursorEngine(self.services)
        return engine.run(goal, execution_mode, on_progress)
