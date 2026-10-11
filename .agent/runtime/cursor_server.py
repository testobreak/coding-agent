# runtime/cursor_server.py
#
# Local Cursor product runtime compatibility wrapper.
# Delegates to the new cursor_runtime application.

import signal
import sys
from runtime.runtime import Runtime
from runtime.server import run_server

class CursorServer:
    """
    Compatibility wrapper for CursorServer.
    Delegates to CursorRuntime under the hood.
    """
    def __init__(self, port: int = 8000):
        self.port = port
        print("[CursorServer] Initializing Local Cursor runtime...")
        self.runtime = Runtime()
        from runtime.server import AgentHTTPHandler
        AgentHTTPHandler._runtime = self.runtime
        print(f"[CursorServer] Ready. Will serve on port {self.port}.")

    def start(self):
        """Start the event-driven HTTP server. Blocks until interrupted."""
        print(f"[CursorServer] Starting server on http://127.0.0.1:{self.port}")
        print("[CursorServer] Waiting for IDE requests...")

        def _handle_sigint(sig, frame):
            print("\n[CursorServer] Shutdown signal received. Exiting cleanly.")
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_sigint)

        try:
            run_server(port=self.port)
        except SystemExit:
            pass
        except Exception as e:
            print(f"[CursorServer] Fatal error: {e}")
            raise
