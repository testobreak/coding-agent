# verify_validation_routing.py
import sys
import os
from pathlib import Path

# Add .agent to path
AGENT_ROOT = Path(__file__).resolve().parent / ".agent"
if AGENT_ROOT.exists() and str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from execution.project_classifier import ProjectClassifier, ProjectType
from execution.validation_router import ValidationRouter, ValidationFailureType

def run_tests():
    print("\n" + "=" * 60)
    print("  Validation Routing & Zero-Test Detection Tests")
    print("=" * 60)

    # Setup dummy directory layout representing a monorepo
    temp_dir = Path("temp_monorepo_test")
    temp_dir.mkdir(exist_ok=True)
    
    backend_dir = temp_dir / "backend"
    backend_dir.mkdir(exist_ok=True)
    (backend_dir / "pom.xml").write_text("<project></project>")

    frontend_dir = temp_dir / "frontend"
    frontend_dir.mkdir(exist_ok=True)
    (frontend_dir / "package.json").write_text("{}")

    scripts_dir = temp_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "requirements.txt").write_text("pytest")

    try:
        classifier = ProjectClassifier()
        
        # Test 1: Monorepo detection
        print("[Test 1] Testing subproject and monorepo detection...")
        units = classifier.detect_subprojects(temp_dir)
        
        assert len(units) == 3, f"Expected 3 subprojects, got {len(units)}"
        unit_roots = {u.root for u in units}
        assert "backend" in unit_roots
        assert "frontend" in unit_roots
        assert "scripts" in unit_roots
        print("  [OK] Successfully classified all monorepo subprojects.")

        # Test 2: Validation Router commands
        print("[Test 2] Testing validation routing commands based on touched files...")
        router = ValidationRouter(temp_dir)
        
        # Touch file in Java backend
        routes = router.route_validation(["backend/src/main/java/Service.java"])
        assert len(routes) == 1
        assert routes[0]["type"] == ProjectType.JAVA_MAVEN
        assert "-pl" in routes[0]["cmd"] and "backend" in routes[0]["cmd"]
        print("  [OK] Successfully routed Java subproject edit to localized mvn command.")

        # Touch file in Node frontend
        routes = router.route_validation(["frontend/src/App.tsx"])
        assert len(routes) == 1
        assert routes[0]["type"] == ProjectType.NODE
        assert routes[0]["cmd"] == ["npm", "test"]
        print("  [OK] Successfully routed Node subproject edit to npm test command.")

        # Test 3: Zero-Test / Fake Validation detection
        print("[Test 3] Testing zero-test run output parsing...")
        
        # Pytest zero tests
        pytest_out = "collected 0 items\n======= no tests ran ======="
        is_valid, reason = ValidationRouter.parse_fake_validation(pytest_out, ProjectType.PYTHON)
        assert not is_valid
        assert "zero tests executed" in reason
        print("  [OK] Successfully detected fake Pytest execution (collected 0 items).")

        # Maven zero tests
        maven_out = "Tests run: 0, Failures: 0, Errors: 0, Skipped: 0"
        is_valid, reason = ValidationRouter.parse_fake_validation(maven_out, ProjectType.JAVA_MAVEN)
        assert not is_valid
        assert "zero tests" in reason
        print("  [OK] Successfully detected fake Maven execution (tests run: 0).")

        # Node zero tests
        node_out = "0 passed, 0 failed, 0 total"
        is_valid, reason = ValidationRouter.parse_fake_validation(node_out, ProjectType.NODE)
        assert not is_valid
        assert "zero tests" in reason
        print("  [OK] Successfully detected fake Vitest/Jest execution (0 passed, 0 failed).")

        # Test 4: Impact-aware validation scope
        print("[Test 4] Testing impact-aware validation scope...")
        impact = router.classify_impact(["backend/src/main/java/Service.java"])
        assert impact["run_backend"] is True
        assert impact["run_frontend"] is False
        assert "backend-only" in impact["reason"]
        print("  [OK] Backend-only edit skips frontend validation.")

        impact = router.classify_impact(["frontend/src/App.tsx"])
        assert impact["run_backend"] is False
        assert impact["run_frontend"] is True
        print("  [OK] Frontend-only edit skips backend validation.")

        impact = router.classify_impact([
            "backend/src/main/java/Service.java",
            "frontend/src/App.tsx",
        ])
        assert impact["run_backend"] is True
        assert impact["run_frontend"] is True
        print("  [OK] Cross-stack edit runs both validations.")

        assert router.should_run_frontend(["backend/src/main/java/Service.java"]) is False
        assert router.should_run_backend(["frontend/src/App.tsx"]) is False
        print("  [OK] should_run_frontend / should_run_backend helpers verified.")

        print("\n" + "=" * 60)
        print("  ALL VALIDATION ROUTING & ROUTER TESTS PASSED! [OK]")
        print("=" * 60 + "\n")

    finally:
        # Cleanup temp layout
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    run_tests()
