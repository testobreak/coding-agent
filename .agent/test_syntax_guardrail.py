# test_syntax_guardrail.py

import os
from execution.validators import ExecutionValidator
from repository.file_manager import FileManager
from memory.state_manager import StateManager
from execution.executor import Executor

print("\n[GUARDRAIL TEST] Initializing Executor & StateManager...")

file_manager = FileManager("..")
state_manager = StateManager()
# Initialize dummy task
state_manager.create_task("Test syntax validation", "syntax_test_session")

executor = Executor(file_manager, state_manager)

# Use paths relative to the sandbox root directory (which is ..)
test_py_file = "syntax_test.py"
test_java_file = "syntax_test.java"

# Resolve native paths for local Python operations
def native_path(f):
    return os.path.join("..", f)

# Ensure clean state
for f in [test_py_file, test_java_file]:
    p = native_path(f)
    if os.path.exists(p):
        os.remove(p)

# ==============================================================================
# TEST 1: Write a valid Python file (Should pass validation)
# ==============================================================================
print("\n" + "=" * 50)
print("TEST 1: Writing VALID Python file...")
print("=" * 50)

valid_python = """
def hello_world():
    print("Hello, world!")
    return True
"""

result1 = executor.execute({
    "action_id": "test-1",
    "tool": "write_file",
    "args": {
        "path": test_py_file,
        "content": valid_python
    }
})

print(f"Result: {result1}")
assert result1["success"] is True, "Valid Python should succeed!"
assert os.path.exists(native_path(test_py_file)), "syntax_test.py must exist!"

# Create a git checkpoint to track the valid version
executor.execute({
    "action_id": "checkpoint-1",
    "tool": "create_checkpoint",
    "args": {"message": "checkpoint:syntax_test.py"}
})

# ==============================================================================
# TEST 2: Modify with INVALID Python syntax (Should fail validation & rollback)
# ==============================================================================
print("\n" + "=" * 50)
print("TEST 2: Modifying with INVALID Python syntax...")
print("=" * 50)

invalid_python = """
def hello_world():
    print("Hello, world!"
    # Missing closing parenthesis!
"""

# We attempt to overwrite using modify_file logic (which triggers validation & rollback)
# For simplicity in this direct mock, we will write invalid content and trigger validate_file_syntax
try:
    print("Testing validator.validate_file_syntax directly with invalid python:")
    # Temporarily write bad content to disk to test validator
    with open(native_path(test_py_file), "w") as f:
        f.write(invalid_python)
        
    executor.validator.validate_file_syntax(executor.file_manager.resolve_path(test_py_file))
    print("ERROR: Validator did not catch Python SyntaxError!")
except Exception as e:
    print(f"SUCCESS: Validator successfully caught SyntaxError:\n  -> {e}")
    # Restore the valid version using rollback_file
    executor.execute({
        "action_id": "rollback-1",
        "tool": "rollback_file",
        "args": {"path": test_py_file}
    })

# Verify file was rolled back to the valid version
with open(native_path(test_py_file), "r") as f:
    restored_content = f.read()

assert "Missing closing parenthesis" not in restored_content, "Rollback failed! Invalid content was kept!"
print("SUCCESS: File was successfully rolled back to original valid version!")


# ==============================================================================
# TEST 3: Write a Java file with unbalanced braces (Should fail brace balance check)
# ==============================================================================
print("\n" + "=" * 50)
print("TEST 3: Writing Java file with UNBALANCED braces...")
print("=" * 50)

invalid_java = """
public class SyntaxTest {
    public void hello() {
        System.out.println("Hello");
    // Missing closing brace for method and class!
"""

# Let's test calling executor.execute directly, which should fail and raise an error
try:
    result3 = executor.execute({
        "action_id": "test-3",
        "tool": "write_file",
        "args": {
            "path": test_java_file,
            "content": invalid_java
        }
    })
    print(f"Executor result: {result3}")
    if not result3.get("success"):
         print(f"SUCCESS: Executor caught java validation error during write_file: {result3.get('error')}")
except Exception as e:
    print(f"SUCCESS: Executor threw error as expected during write_file:\n  -> {e}")

# Verify file does not exist or was rolled back
assert not os.path.exists(native_path(test_java_file)), "Java file with unbalanced braces was not cleaned up!"
print("SUCCESS: Java file was rolled back and deleted!")


# Clean up test files
if os.path.exists(native_path(test_py_file)):
    os.remove(native_path(test_py_file))
# Delete checkpoint commit to keep git log clean
import subprocess
subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd="..", check=False)

print("\n" + "=" * 50)
print("ALL GUARDRAIL TESTS COMPLETED SUCCESSFULLY!")
print("=" * 50)
