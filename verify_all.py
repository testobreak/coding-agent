# verify_all.py
import subprocess
import sys
from pathlib import Path

def run_script(name: str) -> bool:
    print(f"\n============================================================")
    print(f"  RUNNING TEST SUITE: {name}")
    print(f"============================================================")
    try:
        res = subprocess.run([sys.executable, name], capture_output=False, check=True)
        return res.returncode == 0
    except Exception as e:
        print(f"  [ERROR] Suite '{name}' failed with exception: {e}")
        return False

def main():
    suites = [
        "verify_target_resolver.py",
        "verify_query_resolver.py",
        "verify_validation_routing.py",
        "verify_context_engine.py",
        "verify_retrieval_performance.py",
        "verify_retrieval_quality.py",
        "verify_patch_engine.py",
        "verify_server.py",
        "verify_ide_bridge.py",
        "verify_multi_lang_ast.py",
        "verify_patch_modes.py",
        "verify_execution_router.py",
        "verify_local_agent.py"
    ]
    
    results = {}
    for suite in suites:
        if Path(suite).exists():
            success = run_script(suite)
            results[suite] = "PASSED [OK]" if success else "FAILED [ERROR]"
        else:
            results[suite] = "SKIPPED [NOT FOUND]"
            
    print("\n============================================================")
    print("  VERIFICATION DASHBOARD SUMMARY")
    print("============================================================")
    all_ok = True
    for suite, status in results.items():
        print(f"  - {suite:35s} : {status}")
        if "FAILED" in status:
            all_ok = False
            
    print("============================================================")
    if all_ok:
        print("  ALL CORE BACKEND VERIFICATION CHECKS PASSED! [100% GREEN]")
    else:
        print("  SOME CHECKS ENCOUNTERED ERRORS.")
    print("============================================================\n")
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
