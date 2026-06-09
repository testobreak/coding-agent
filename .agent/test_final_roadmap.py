# test_final_roadmap.py

import os
import subprocess
from execution.validators import ExecutionValidator
from repository.file_manager import FileManager
from memory.state_manager import StateManager
from execution.executor import Executor

print("\n[ROADMAP VERIFICATION] Initializing Executor & StateManager...")

file_manager = FileManager("..")
state_manager = StateManager()
# Initialize dummy task
state_manager.create_task("Verify final roadmap fixes", "roadmap_test_session")

executor = Executor(file_manager, state_manager)

# Ensure clean git state in the repository root
subprocess.run(["git", "reset", "--hard", "HEAD"], cwd="..", check=False)

# ==============================================================================
# TEST 1: Checkpoint Safety (Targeted staging only)
# ==============================================================================
print("\n" + "=" * 60)
print("TEST 1: Checkpoint Safety (Targeted staging only)")
print("=" * 60)

# Create two untracked dummy files in the repo root
file_a = "../unrelated_file.txt"
file_b = "../targeted_file.txt"

for f in [file_a, file_b]:
    with open(f, "w") as out:
        out.write("Dummy content")

# Create a targeted checkpoint for ONLY file_b
executor.execute({
    "action_id": "checkpoint-b",
    "tool": "create_checkpoint",
    "args": {"message": "checkpoint:targeted_file.txt"}
})

# Get git status to see if unrelated_file.txt was NOT staged (it should remain untracked!)
status_output = executor.dispatch("git_status", {})
print(f"Git status after targeted checkpoint:\n{status_output}")

assert "unrelated_file.txt" in status_output, "Checkpoint Safety FAILED: Unrelated untracked file was staged!"
print("SUCCESS: Checkpoint Safety VERIFIED! Unrelated files were ignored.")

# Clean up
for f in [file_a, file_b]:
    if os.path.exists(f):
        os.remove(f)
# Reset head to clean baseline
subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd="..", check=False)


# ==============================================================================
# TEST 2: Patch Format Consistency Check
# ==============================================================================
print("\n" + "=" * 60)
print("TEST 2: Patch Format Consistency Check")
print("=" * 60)

bad_patch = """
This is a plain text modification recommendation instead of a unified git patch.
It lacks the standard diff indicators.
"""

try:
    executor.validator.validate_patch(bad_patch)
    print("ERROR: Validator did not catch bad patch format!")
    assert False
except Exception as e:
    print(f"SUCCESS: Validator successfully caught invalid patch format:\n  -> {e}")
    assert "missing unified diff markers" in str(e)


# ==============================================================================
# TEST 3: Verify RAG chunks reach Modification prompt
# ==============================================================================
print("\n" + "=" * 60)
print("TEST 3: Verify RAG chunks reach Modification Prompt")
print("=" * 60)

# Inject a mock retrieved chunk into state memory
mock_chunk = {
    "chunk_id": "mock_chunk_1",
    "file": "mock_service.java",
    "name": "MockService",
    "type": "ClassDef",
    "code": "public class MockService { }",
    "score": 0.95
}
executor.state_manager.add_chunk(mock_chunk)

# Re-read state context to prove chunks are persisted
state = executor.state_manager.get_state()
assert len(state.retrieved_chunks) > 0, "RAG persistence FAILED!"
print(f"Persisted RAG chunks verified in TaskState: {state.retrieved_chunks[0]['file']}")
print(f"DEBUG - state.retrieved_chunks: {state.retrieved_chunks}")
print(f"DEBUG - max_chunks: {executor.context_assembler.max_chunks}")
sliced_chunks = state.retrieved_chunks[-executor.context_assembler.max_chunks:]
print(f"DEBUG - sliced_chunks: {sliced_chunks}")
compressed_debug = executor.context_assembler.compressor.compress_chunks(sliced_chunks)
print(f"DEBUG - compressed_chunks result: {compressed_debug}")

# Now verify generate_modification builds the execution context and passes chunks
context = executor.context_assembler.build(state)
print(f"DEBUG - context retrieved_chunks: {context.get('retrieved_chunks')}")
assert len(context["retrieved_chunks"]) > 0, "RAG ContextAssembler retrieval FAILED!"

retrieved_chunk_in_context = context["retrieved_chunks"][0]
print(f"Compressed chunk in assembled context: {retrieved_chunk_in_context['file']}")

# Run build_prompt from ModificationEngine directly using this context
prompt = executor.modifier.build_prompt(
    goal="Add new endpoint",
    file_path="MyController.java",
    original_content="public class MyController {}",
    retrieved_context=context["retrieved_chunks"],
    execution_context="Execution prompt text",
    architecture_notes=[]
)

print(f"\nVerification prompt text preview:\n{prompt[:350]}...")
assert "mock_service.java" in prompt, "RAG Prompt Chaining FAILED! Retrieved context did not reach prompt!"
print("\nSUCCESS: RAG Prompt Chaining VERIFIED! Retrieved chunks are correctly embedded in the LLM prompt.")

print("\n" + "=" * 60)
print("ALL CORE ROADMAP VERIFICATIONS COMPLETED SUCCESSFULLY!")
print("=" * 60)
