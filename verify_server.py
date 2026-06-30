# verify_server.py
#
# Integration tests for Agent HTTP Server endpoints (/chat, /retrieve, /apply_patch, /diagnostics).

import sys
import os
import time
import json
import urllib.request
import urllib.error
import subprocess
from pathlib import Path

# Add .agent to path so we can import modules if needed
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from repository_intelligence.db.connection import SessionLocal, Base, engine
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.file import File
from repository_intelligence.models.symbol import Symbol

def run_tests():
    print("\n" + "=" * 60)
    print("  Agent Local API Server Integration Verification")
    print("=" * 60)

    # Initialize schema
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    # Create mock entities
    repo = Repository(name="HRMS-Server", root_path=os.getcwd())
    session.add(repo)
    session.flush()

    file_row = File(
        repository_id=repo.id,
        path="backend/src/main/java/com/hrms/employee/EmployeeService.java",
        language="java",
        file_hash="mock_hash_server",
        size_bytes=1000
    )
    session.add(file_row)
    session.flush()

    symbol_row = Symbol(
        repository_id=repo.id,
        file_id=file_row.id,
        name="EmployeeService",
        qualified_name="com.hrms.employee.EmployeeService",
        symbol_type="class",
        start_line=1,
        end_line=20,
        source_hash="mock_source_hash_server"
    )
    session.add(symbol_row)
    session.flush()
    session.commit()

    # Write mock file content
    mock_file_path = Path(os.getcwd()) / file_row.path
    mock_file_path.parent.mkdir(parents=True, exist_ok=True)
    mock_file_path.write_text("package com.hrms.employee;\npublic class EmployeeService {\n    // line 3\n}\n", encoding="utf-8")

    server_process = None
    try:
        # Start server in the background
        print("[ServerTest] Launching runtime.server in a background process...")
        # Open log files
        stdout_f = open("server_stdout.log", "w")
        stderr_f = open("server_stderr.log", "w")
        server_process = subprocess.Popen(
            [sys.executable, "-u", "-m", "runtime.server", "8085"],
            cwd=str(AGENT_ROOT),
            stdout=stdout_f,
            stderr=stderr_f
        )
        # Poll the server until it is ready
        print("[ServerTest] Waiting for server to start listening...")
        server_ready = False
        for attempt in range(15):
            try:
                # Test connection
                req = urllib.request.Request("http://127.0.0.1:8085/diagnostics", data=json.dumps({"diagnostics": []}).encode('utf-8'), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=1.0) as conn:
                    conn.read()
                server_ready = True
                print(f"  [OK] Server is ready after {attempt + 1} attempts.")
                break
            except Exception:
                time.sleep(1.0)

        if not server_ready:
            raise RuntimeError("Server failed to start listening within 15 seconds.")

        # -------------------------------------------------------------
        # TEST 1: Register Diagnostics
        # -------------------------------------------------------------
        print("\n[Test 1] Sending active file diagnostics to /diagnostics...")
        diag_payload = {
            "diagnostics": [
                {
                    "file": file_row.path,
                    "line": 3,
                    "severity": "error",
                    "message": "Syntax error: missing semicolon",
                    "source": "javac"
                }
            ]
        }
        
        req = urllib.request.Request(
            "http://127.0.0.1:8085/diagnostics",
            data=json.dumps(diag_payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            data = json.loads(res.read().decode('utf-8'))
            assert data["status"] == "registered"
            assert data["count"] == 1
            # Check CORS header
            assert res.headers.get("Access-Control-Allow-Origin") == "*"
            print("  [OK] /diagnostics registered successfully with CORS.")

        # -------------------------------------------------------------
        # TEST 2: Context Retrieval
        # -------------------------------------------------------------
        print("\n[Test 2] Querying planning context from /retrieve...")
        retrieve_payload = {
            "query": "explain EmployeeService",
            "editor_context": {
                "active_file": file_row.path,
                "cursor_line": 3,
                "cursor_column": 4,
                "open_tabs": [file_row.path]
            }
        }
        
        req = urllib.request.Request(
            "http://127.0.0.1:8085/retrieve",
            data=json.dumps(retrieve_payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            data = json.loads(res.read().decode('utf-8'))
            print("RETRIEVED DATA:", json.dumps(data, indent=2))
            assert data["goal"] == "explain EmployeeService"
            assert data["primary_symbol"]["fqn"] in ("com.hrms.employee.EmployeeService", "EmployeeService")
            assert len(data["snippets"]) > 0
            print("  [OK] /retrieve returns compiled context successfully.")

        # -------------------------------------------------------------
        # TEST 3: Apply Patch
        # -------------------------------------------------------------
        print("\n[Test 3] Requesting SEARCH/REPLACE patch application on /apply_patch...")
        
        temp_test_file = Path(os.getcwd()) / "temp_patch_test.py"
        temp_test_file.write_text("def run():\n    print('hello')\n", encoding="utf-8")
        
        patch_text = "<<<<<<< SEARCH\ndef run():\n    print('hello')\n=======\ndef run():\n    print('patched!')\n>>>>>>> REPLACE"
        
        patch_payload = {
            "file_path": str(temp_test_file),
            "patch": patch_text
        }
        
        req = urllib.request.Request(
            "http://127.0.0.1:8085/apply_patch",
            data=json.dumps(patch_payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            data = json.loads(res.read().decode('utf-8'))
            assert data["status"] == "applied"
            
            # Check file content
            patched_content = temp_test_file.read_text(encoding="utf-8")
            assert "print('patched!')" in patched_content
            print("  [OK] /apply_patch applied patch and updated file successfully.")

        if temp_test_file.exists():
            temp_test_file.unlink()

        # -------------------------------------------------------------
        # TEST 4: Editor State Bridge (/editor/state GET and POST)
        # -------------------------------------------------------------
        print("\n[Test 4] Verifying Editor State Bridge API on /editor/state...")
        editor_payload = {
            "workspace_root": os.getcwd(),
            "active_file": file_row.path,
            "cursor_line": 3,
            "cursor_column": 4,
            "selected_text": "public class EmployeeService",
            "unsaved_buffer": "some unsaved edits",
            "diagnostics": [
                {
                    "severity": "error",
                    "message": "Syntax error",
                    "line": 3,
                    "column": 0,
                    "source": "javac"
                }
            ]
        }
        
        # Test POST
        req = urllib.request.Request(
            "http://127.0.0.1:8085/editor/state",
            data=json.dumps(editor_payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            data = json.loads(res.read().decode('utf-8'))
            assert data["status"] == "ok"
            print("  [OK] POST /editor/state registered state successfully.")

        # Test GET
        req = urllib.request.Request(
            "http://127.0.0.1:8085/editor/state"
        )
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            data = json.loads(res.read().decode('utf-8'))
            assert data["active_file"] == file_row.path
            assert data["unsaved_buffer"] == "some unsaved edits"
            assert len(data["diagnostics"]) == 1
            assert data["diagnostics"][0]["message"] == "Syntax error"
            print("  [OK] GET /editor/state retrieved state successfully.")

        # -------------------------------------------------------------
        # TEST 5: Apply Patches Protocol (/editor/apply_patches)
        # -------------------------------------------------------------
        print("\n[Test 5] Verifying structured apply patches protocol on /editor/apply_patches...")
        temp_patches_file = Path(os.getcwd()) / "temp_patches_test.py"
        temp_patches_file.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        patches_payload = {
            "patches": [
                {
                    "file_path": str(temp_patches_file),
                    "start_line": 2,
                    "end_line": 2,
                    "replacement": "patched line 2"
                }
            ]
        }

        req = urllib.request.Request(
            "http://127.0.0.1:8085/editor/apply_patches",
            data=json.dumps(patches_payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            data = json.loads(res.read().decode('utf-8'))
            assert data["status"] == "applied"
            assert data["count"] == 1

            # Verify contents
            content = temp_patches_file.read_text(encoding="utf-8")
            assert "patched line 2" in content
            assert "line 1" in content
            assert "line 3" in content
            print("  [OK] POST /editor/apply_patches applied structured patches successfully.")

        if temp_patches_file.exists():
            temp_patches_file.unlink()

        print("\n" + "=" * 60)
        print("  ALL API SERVER INTEGRATION TESTS PASSED SUCCESSFULLY! [OK]")
        print("=" * 60 + "\n")

    except AssertionError as ae:
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except urllib.error.URLError as ue:
        print(f"\n[FAIL] HTTP CONNECTION FAILED: {ue}")
        # Allow process to finish writing logs
        time.sleep(1.0)
        try:
            stdout_f.flush()
            stderr_f.flush()
            if os.path.exists("server_stderr.log"):
                print("\nServer process STDERR:")
                with open("server_stderr.log", "r") as f:
                    print(f.read())
            if os.path.exists("server_stdout.log"):
                print("\nServer process STDOUT:")
                with open("server_stdout.log", "r") as f:
                    print(f.read())
        except Exception as ex:
            print("Failed to read server logs:", ex)
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] EXCEPTION ENCOUNTERED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Kill server process
        if server_process:
            print("[ServerTest] Terminating backend server...")
            server_process.terminate()
            server_process.wait()
            
        # Close and remove log files
        try:
            stdout_f.close()
            stderr_f.close()
            if os.path.exists("server_stdout.log"): os.remove("server_stdout.log")
            if os.path.exists("server_stderr.log"): os.remove("server_stderr.log")
        except Exception:
            pass
            
        # Cleanup mock file
        if mock_file_path.exists():
            mock_file_path.unlink()
        
        # Clean DB mock data
        session.delete(symbol_row)
        session.delete(file_row)
        session.delete(repo)
        session.commit()
        session.close()

if __name__ == "__main__":
    run_tests()
