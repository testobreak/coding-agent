# runtime/server.py
#
# Zero-dependency local agent API server running on localhost:8000.
# Handles CORS and JSON routing to integrate the backend runtime with the VS Code extension.

import json
import os
import sys
from http.server import ThreadingHTTPServer as HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

# Setup path so we can import from agent modules
AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from runtime.runtime import Runtime
from runtime.editor.models import RuntimeContext, Diagnostic
from editing.symbol_handle import SymbolHandle
from editing.patch_applier import PatchApplier

class AgentHTTPHandler(BaseHTTPRequestHandler):
    _runtime = None
    _latest_editor_state = {}

    @classmethod
    def get_runtime(cls):
        if cls._runtime is None:
            cls._runtime = Runtime()
        return cls._runtime

    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _set_sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        if self.path == "/editor/state":
            self._set_headers(200)
            self.wfile.write(json.dumps(AgentHTTPHandler._latest_editor_state).encode('utf-8'))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            payload = json.loads(post_data) if post_data else {}
        except Exception as e:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {e}"}).encode('utf-8'))
            return

        if self.path == "/chat":
            self.handle_chat(payload)
        elif self.path == "/retrieve":
            self.handle_retrieve(payload)
        elif self.path == "/modify":
            self.handle_modify(payload)
        elif self.path == "/apply_patch":
            self.handle_apply_patch(payload)
        elif self.path == "/diagnostics":
            self.handle_diagnostics(payload)
        elif self.path == "/editor/state":
            AgentHTTPHandler._latest_editor_state = payload
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
        elif self.path == "/editor/apply_patches":
            self.handle_apply_patches(payload)
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode('utf-8'))

    def handle_chat(self, payload):
        query = payload.get("query")
        if not query:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Missing 'query' field"}).encode('utf-8'))
            return

        runtime = self.get_runtime()
        editor_context_json = payload.get("editor_context", {})
        
        # Map editor context
        runtime_ctx = self._map_editor_context(editor_context_json)
        
        self._set_sse_headers()

        def on_progress(event_type, content):
            data = json.dumps({"type": event_type, "content": content})
            try:
                self.wfile.write(f"data: {data}\n\n".encode('utf-8'))
                self.wfile.flush()
            except Exception:
                pass

        # Route query using Intent Router
        from runtime.fast_path_router import FastPathRouter
        from routing.intent_router import ExecutionMode
        
        route_decision = FastPathRouter.route(query, runtime_ctx)
        mode = route_decision.execution_mode

        try:
            if mode == ExecutionMode.INLINE:
                from execution.inline_executor import InlineExecutor
                engine = InlineExecutor(runtime)
                res = engine.run(query, runtime_ctx, on_progress=on_progress)
                on_progress("done", {"status": "success", "response": res})
                
            elif mode in (ExecutionMode.ASSIST, ExecutionMode.ANALYZE):
                from execution.assist_executor import AssistExecutor
                engine = AssistExecutor(runtime)
                res = engine.run(query, runtime_ctx, on_progress=on_progress)
                on_progress("done", {"status": "success", "response": res})
                
            elif mode == ExecutionMode.PATCH:
                from execution.patch_executor import PatchExecutor
                handler = PatchExecutor(runtime)
                res = handler.run(query, runtime_ctx, on_progress=on_progress)
                on_progress("done", {
                    "status": "success" if res.get("success") else "failed",
                    "patch": res.get("patch"),
                    "file_path": res.get("file_path")
                })
                
            else: # ExecutionMode.AGENT
                raise RuntimeError("Agent mode is not supported by Local Cursor's pure Cursor runtime.")
        except Exception as e:
            try:
                import traceback
                traceback.print_exc()
                data = json.dumps({"type": "error", "content": f"Execution failed: {e}"})
                self.wfile.write(f"data: {data}\n\n".encode('utf-8'))
                self.wfile.flush()
            except Exception:
                pass

    def handle_retrieve(self, payload):
        query = payload.get("query")
        if not query:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Missing 'query' field"}).encode('utf-8'))
            return

        runtime = self.get_runtime()
        editor_context_json = payload.get("editor_context", {})
        runtime_ctx = self._map_editor_context(editor_context_json)

        try:
            from runtime.fast_path_router import FastPathRouter
            from context.context_builder import ContextBuilder
            
            route_decision = FastPathRouter.route(query, runtime_ctx)
            mode = route_decision.execution_mode
            
            # Build mock state to hold runtime context
            class MockState:
                def __init__(self, rc):
                    self.runtime_context = rc
                    self.session_id = "default"
                    self.open_files = []
            
            state = MockState(runtime_ctx)
            builder = ContextBuilder(runtime.executor.retrieval_pipeline, runtime.state_manager)
            pkg = builder.build_planning_context(query, state=state, mode=mode.value)
            
            # Serialize planning context
            response_data = {
                "goal": pkg.goal,
                "primary_symbol": self._serialize_symbol(pkg.primary_symbol),
                "callers": [self._serialize_symbol(c) for c in pkg.callers],
                "callees": [self._serialize_symbol(c) for c in pkg.callees],
                "related_tests": [self._serialize_symbol(t) for t in pkg.related_tests],
                "imports": pkg.imports,
                "snippets": [
                    {
                        "symbol": s.symbol,
                        "source": s.source,
                        "relevance": s.relevance
                    }
                    for s in pkg.snippets
                ]
            }
            self._set_headers(200)
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": f"Retrieval failed: {e}"}).encode('utf-8'))

    def handle_modify(self, payload):
        query = payload.get("query")
        editor_context_json = payload.get("editor_context", {})
        
        runtime = self.get_runtime()
        runtime_ctx = self._map_editor_context(editor_context_json)

        self._set_sse_headers()

        def on_progress(event_type, content):
            data = json.dumps({"type": event_type, "content": content})
            try:
                self.wfile.write(f"data: {data}\n\n".encode('utf-8'))
                self.wfile.flush()
            except Exception:
                pass

        try:
            task_id = str(os.urandom(16).hex())
            state = runtime.state_manager.create_task(goal=query, task_id=task_id)
            state.runtime_context = runtime_ctx
            
            # Compile plan & run patch edits with progress stream
            runtime.run_goal(query, on_progress=on_progress)
            
            # Collect diffs
            pending = getattr(runtime.state_manager, "pending_patch", None)
            response_data = {
                "status": "success",
                "task_id": task_id,
                "patch": pending.get("patch") if pending else None,
                "file_path": pending.get("file_path") if pending else None
            }
            on_progress("done", response_data)
        except Exception as e:
            try:
                data = json.dumps({"type": "error", "content": f"Modification failed: {e}"})
                self.wfile.write(f"data: {data}\n\n".encode('utf-8'))
                self.wfile.flush()
            except Exception:
                pass

    def handle_apply_patch(self, payload):
        file_path = payload.get("file_path")
        patch = payload.get("patch")
        if not file_path or not patch:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Missing 'file_path' or 'patch' field"}).encode('utf-8'))
            return

        try:
            runtime = self.get_runtime()
            applier = PatchApplier()
            content = runtime.file_manager.read_file(file_path)
                
            try:
                new_content = applier.apply(content, patch)
                runtime.file_manager.write_file(file_path, new_content)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "applied"}).encode('utf-8'))
            except ValueError as ve:
                self._set_headers(422)
                self.wfile.write(json.dumps({"error": str(ve)}).encode('utf-8'))
        except Exception as e:
            self._set_headers(500)
            import traceback
            traceback.print_exc()
            self.wfile.write(json.dumps({"error": f"Patch application error: {e}"}).encode('utf-8'))

    def handle_diagnostics(self, payload):
        # Simply cache diagnostics
        diagnostics_json = payload.get("diagnostics", [])
        from context.session_cache import SessionCache
        session_ctx = SessionCache.get_session("default")
        
        session_ctx.diagnostics = []
        for d in diagnostics_json:
            session_ctx.diagnostics.append(Diagnostic(
                file=d.get("file", ""),
                line=d.get("line", 0),
                severity=d.get("severity", "error"),
                message=d.get("message", ""),
                source=d.get("source", "")
            ))
        
        self._set_headers(200)
        self.wfile.write(json.dumps({"status": "registered", "count": len(session_ctx.diagnostics)}).encode('utf-8'))

    # Helper methods
    def _map_editor_context(self, ctx_json) -> RuntimeContext:
        if not ctx_json:
            return RuntimeContext()
            
        diagnostics = []
        for d in ctx_json.get("diagnostics", []):
            diagnostics.append(Diagnostic(
                file=d.get("file", ""),
                line=d.get("line", 0),
                severity=d.get("severity", ""),
                message=d.get("message", ""),
                source=d.get("source", "")
            ))
            
        cursor_pos = None
        cursor_offset = ctx_json.get("cursor_position")
        active_file = ctx_json.get("active_file")
        
        if "cursor_line" in ctx_json:
            cursor_pos = (ctx_json["cursor_line"], ctx_json.get("cursor_column", 0))
        elif cursor_offset is not None and active_file:
            try:
                import os
                repo_root = os.getcwd()
                if os.path.basename(repo_root) == ".agent":
                    repo_root = os.path.dirname(repo_root)
                full_path = os.path.join(repo_root, active_file)
                
                content = ctx_json.get("unsaved_buffer")
                if not content and os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                        
                if content:
                    lines = content[:cursor_offset].splitlines()
                    line_num = len(lines) if lines else 1
                    col_num = len(lines[-1]) if lines else 0
                    cursor_pos = (line_num, col_num)
            except Exception:
                pass
            
        sel_range = None
        if "selection_range" in ctx_json:
            r = ctx_json["selection_range"]
            try:
                sel_range = ((r[0][0], r[0][1]), (r[1][0], r[1][1]))
            except Exception:
                pass

        # Build client-specific IDEContext via IDEBridge adapter
        from ide.bridge import IDEBridge
        client_name = ctx_json.get("client") or ""
        adapter = IDEBridge.get_adapter(client_name)
        ide_ctx = adapter.parse_payload(ctx_json)

        # Update VirtualWorkspace if unsaved buffer is provided
        if active_file:
            import os
            repo_root = os.getcwd()
            if os.path.basename(repo_root) == ".agent":
                repo_root = os.path.dirname(repo_root)
            full_path = os.path.abspath(os.path.join(repo_root, active_file))
            
            unsaved = ctx_json.get("unsaved_buffer")
            if unsaved is not None:
                from ide.virtual_workspace import VirtualWorkspace
                VirtualWorkspace.get_instance().set_buffer(full_path, unsaved)

        return RuntimeContext(
            active_file=active_file,
            cursor_position=cursor_pos,
            selection=ctx_json.get("selection") or ctx_json.get("selected_text"),
            selection_range=sel_range,
            open_tabs=ctx_json.get("open_tabs", []),
            diagnostics=diagnostics,
            visible_range=ctx_json.get("visible_range"),
            unsaved_buffer=ctx_json.get("unsaved_buffer"),
            ide_context=ide_ctx
        )

    def handle_apply_patches(self, payload):
        patches = payload.get("patches", [])
        if not patches:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Missing 'patches' list"}).encode('utf-8'))
            return

        try:
            from collections import defaultdict
            file_edits = defaultdict(list)
            for p in patches:
                file_edits[p["file_path"]].append(p)

            for file_path, edits in file_edits.items():
                if not os.path.exists(file_path):
                    continue
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content_lines = f.read().splitlines()

                # Apply edits in reverse order of start_line to avoid shifting line numbers
                edits.sort(key=lambda e: e["start_line"], reverse=True)
                for edit in edits:
                    start = max(0, edit["start_line"] - 1)
                    end = max(0, edit["end_line"])
                    replacement_lines = edit["replacement"].splitlines()
                    content_lines[start:end] = replacement_lines

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(content_lines) + "\n")

            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "applied", "count": len(patches)}).encode('utf-8'))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": f"Failed to apply patches: {e}"}).encode('utf-8'))

    def _serialize_symbol(self, handle: Optional[SymbolHandle]):
        if not handle:
            return None
        return {
            "symbol_id": handle.symbol_id,
            "fqn": handle.fqn,
            "kind": handle.kind,
            "file_path": handle.file_path,
            "start_line": handle.start_line,
            "end_line": handle.end_line
        }

def run_server(port=8000):
    import socket
    # Pre-flight availability check
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
    except OSError:
        print(f"[CursorServer] Error: Port {port} is already in use by another process.")
        print(f"[CursorServer] Please check running processes (e.g. run: lsof -i :{port}) and terminate any existing instances.")
        sys.exit(1)
    finally:
        sock.close()

    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, AgentHTTPHandler)
    print(f"[CursorServer] Server running on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[CursorServer] Stopping server...")
        httpd.server_close()

if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
