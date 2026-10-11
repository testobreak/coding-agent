import os
import sys

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".agent"
    )
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ide.bridge import IDEBridge, VSCodeAdapter, JetBrainsAdapter, NeovimAdapter

def test_vscode_adapter():
    print("[Test] Verifying VSCodeAdapter...")
    adapter = IDEBridge.get_adapter("vscode")
    assert isinstance(adapter, VSCodeAdapter)

    raw = {
        "active_file": "src/main.ts",
        "cursor_position": 10,
        "selection": "const x = 5;",
        "diagnostics": [],
        "open_tabs": ["src/main.ts", "package.json"]
    }
    context = adapter.parse_payload(raw)
    assert context.active_file == "src/main.ts"
    assert context.cursor_line == 10
    assert context.selected_text == "const x = 5;"
    assert context.open_tabs == ["src/main.ts", "package.json"]

    # Verify EditorState parsing
    state = adapter.parse_editor_state(raw)
    assert state.active_file == "src/main.ts"
    assert state.cursor_line == 10
    assert state.selected_text == "const x = 5;"
    assert state.open_tabs == ["src/main.ts", "package.json"]

    proposal = adapter.format_proposal("src/main.ts", "const x = 4;", "const x = 5;")
    assert proposal["client"] == "vscode"
    assert proposal["action"] == "diff_preview"
    assert proposal["original"] == "const x = 4;"
    print("  [OK] VSCodeAdapter verified.")


def test_jetbrains_adapter():
    print("[Test] Verifying JetBrainsAdapter...")
    adapter = IDEBridge.get_adapter("jetbrains-idea")
    assert isinstance(adapter, JetBrainsAdapter)

    raw = {
        "client": "jetbrains",
        "active_file": "src/main/Employee.java",
        "cursor_position": 0,  # 0-indexed cursor position from IntelliJ
        "selected_text": "public class Employee",
        "diagnostics": []
    }
    context = adapter.parse_payload(raw)
    assert context.cursor_line == 1  # Shifted to 1-indexed for backend

    # Verify EditorState parsing (ensures IntelliJ 0-index shift)
    state = adapter.parse_editor_state(raw)
    assert state.cursor_line == 1

    proposal = adapter.format_proposal("src/main/Employee.java", "class E {}", "public class Employee {}")
    assert proposal["client"] == "jetbrains"
    assert proposal["action"] == "show_side_by_side"
    print("  [OK] JetBrainsAdapter verified.")


def test_neovim_adapter():
    print("[Test] Verifying NeovimAdapter...")
    adapter = IDEBridge.get_adapter("neovim")
    assert isinstance(adapter, NeovimAdapter)

    raw = {
        "client": "neovim",
        "active_file": "app.py",
        "cursor_position": 12,
        "diagnostics": [
            {"filename": "app.py", "lnum": 5, "text": "SyntaxError: invalid syntax"}
        ]
    }
    context = adapter.parse_payload(raw)
    assert len(context.diagnostics) == 1
    assert context.diagnostics[0]["file"] == "app.py"
    assert context.diagnostics[0]["line"] == 5
    assert context.diagnostics[0]["message"] == "SyntaxError: invalid syntax"

    # Verify EditorState parsing
    state = adapter.parse_editor_state(raw)
    assert len(state.diagnostics) == 1
    assert state.diagnostics[0].line == 5
    assert state.diagnostics[0].message == "SyntaxError: invalid syntax"

    proposal = adapter.format_proposal("app.py", "print(1)", "print(2)")
    assert proposal["client"] == "neovim"
    assert proposal["action"] == "unified_diff"
    assert "a/app.py" in proposal["diff"]
    assert "+print(2)" in proposal["diff"]
    print("  [OK] NeovimAdapter verified.")


def main():
    print("============================================================")
    print("  IDE Bridge & Extension Adapter Verification Suite")
    print("============================================================")
    try:
        test_vscode_adapter()
        test_jetbrains_adapter()
        test_neovim_adapter()
        print("============================================================")
        print("  ALL IDE ADAPTER CHECKS PASSED SUCCESSFULLY! [OK]")
        print("============================================================\n")
        sys.exit(0)
    except AssertionError as ae:
        print(f"  [ERROR] Assertion failed: {ae}")
        sys.exit(1)

if __name__ == "__main__":
    main()
