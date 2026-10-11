# main.py
#
# Local Cursor / Agent unified entrypoint.
#
# Mode is controlled via AGENT_MODE environment variable:
#   AGENT_MODE=local_cursor  (default) → start HTTP server for VS Code extension
#   AGENT_MODE=agent                   → start autonomous agent runtime (CLI)
#
# Examples:
#   python3 main.py                         # Local Cursor (default)
#   AGENT_MODE=agent python3 main.py        # Autonomous agent

import os
import sys

# Setup sys.path so we can import from core/apps and root directory
AGENT_ROOT = os.path.abspath(os.path.dirname(__file__))
if AGENT_ROOT not in sys.path:
    sys.path.insert(0, AGENT_ROOT)

PARENT_DIR = os.path.dirname(AGENT_ROOT)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def main():
    from core.bootstrap import bootstrap
    from core.execution_mode import ExecutionMode
    from apps.cursor_runtime import CursorRuntime

    port = int(os.getenv("CURSOR_PORT", "8000"))
    services = bootstrap(ExecutionMode.CURSOR)
    runtime = CursorRuntime(services, port=port)
    runtime.start()

if __name__ == "__main__":
    main()
