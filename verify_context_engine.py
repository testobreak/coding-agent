# verify_context_engine.py
import sys
from pathlib import Path

# Add .agent to path
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

# Also add workspace root for repository_intelligence imports
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from repository_intelligence.workspace import Workspace, WorkspaceType
from repository_intelligence.workspace_scanner import WorkspaceScanner
from execution.workspace_resolver import WorkspaceResolver
from execution.tool_router import ToolRouter
from execution.context_engine import ExecutionContextEngine, WorkspaceRoutingError

def test_engine():
    print("\n" + "=" * 60)
    print("  Execution Context Engine & Workspace Routing Verification")
    print("=" * 60)

    # 1. Setup temp mock monorepo structure
    temp_root = Path("temp_context_monorepo")
    temp_root.mkdir(exist_ok=True)

    backend = temp_root / "backend"
    backend.mkdir(exist_ok=True)
    (backend / "pom.xml").write_text("<project></project>")

    frontend = temp_root / "frontend"
    frontend.mkdir(exist_ok=True)
    (frontend / "package.json").write_text("{}")

    nested_app = frontend / "apps" / "admin"
    nested_app.mkdir(parents=True, exist_ok=True)
    (nested_app / "package.json").write_text("{}")

    try:
        # 2. Test Workspace Scanner
        print("[Test 1] Testing workspace scanner with nested structures...")
        scanner = WorkspaceScanner()
        workspaces = scanner.scan(temp_root)
        
        assert len(workspaces) == 3, f"Expected 3 workspaces, found {len(workspaces)}"
        ws_names = {w.name for w in workspaces}
        assert "backend" in ws_names
        assert "frontend" in ws_names
        assert "frontend/apps/admin" in ws_names or "frontend\\apps\\admin" in ws_names
        print("  [OK] Successfully scanned and identified nested monorepo structures.")

        # 3. Test Workspace Resolver (deepest match resolution)
        print("[Test 2] Testing workspace resolver (deepest match resolution)...")
        resolver = WorkspaceResolver(workspaces)
        
        # Simple match
        ws_backend = resolver.resolve_for_file(str(backend / "src" / "main" / "java" / "Service.java"))
        assert ws_backend is not None
        assert ws_backend.type == WorkspaceType.JAVA_MAVEN
        assert ws_backend.name == "backend"

        # Nested match - must resolve to deepest apps/admin, not parent frontend
        ws_nested = resolver.resolve_for_file(str(nested_app / "src" / "index.ts"))
        assert ws_nested is not None
        assert ws_nested.name in ("frontend/apps/admin", "frontend\\apps\\admin")
        print("  [OK] Deepest match path resolution works correctly (nested workspaces).")

        # 4. Test Tool Router
        print("[Test 3] Testing workspace command routing...")
        router = ToolRouter()
        
        maven_ws = next(w for w in workspaces if w.type == WorkspaceType.JAVA_MAVEN)
        cmd = router.build_command(maven_ws, "test")
        assert "mvn" in cmd
        
        node_ws = next(w for w in workspaces if w.type == WorkspaceType.NODE and w.name == "frontend")
        cmd_node = router.build_command(node_ws, "build")
        assert cmd_node == ["npm", "run", "build"]
        print("  [OK] Workspace commands mapped correctly.")

        # 5. Test ExecutionContextEngine caching and fail-fast routing
        print("[Test 4] Testing ExecutionContextEngine caching & fail-fast...")
        engine = ExecutionContextEngine(temp_root)
        
        # Verify cache file was created
        cache_file = temp_root / ".agent" / "workspaces_metadata.json"
        assert cache_file.exists()
        print("  [OK] Context engine successfully persisted metadata cache to disk.")

        # Fail fast resolution
        try:
            engine.resolve_workspace("/some/random/nonexistent/file.txt")
            assert False, "Expected WorkspaceRoutingError for untracked paths"
        except WorkspaceRoutingError:
            print("  [OK] Context engine failed-fast with WorkspaceRoutingError for untracked paths.")

        print("\n" + "=" * 60)
        print("  ALL EXECUTION CONTEXT ENGINE CHECKS PASSED! [OK]")
        print("=" * 60 + "\n")

    finally:
        import shutil
        if temp_root.exists():
            shutil.rmtree(temp_root)

if __name__ == "__main__":
    test_engine()
