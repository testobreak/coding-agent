import os
import json
import re

brain_dir = r"C:\Users\ashish\.gemini\antigravity\brain"
print("Scanning all transcripts for verify_transaction.py...")

found_count = 0
for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file == "transcript.jsonl":
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for idx, line in enumerate(f):
                        if "verify_transaction.py" in line:
                            # Let's inspect the line
                            if "class MockFileManager" in line or "class MockStateManager" in line:
                                print(f"Found match in {path} at line {idx}, length: {len(line)}")
                                # Let's save a snippet or find if it contains the full text
                                out_path = f"verify_tx_candidate_{found_count}.txt"
                                with open(out_path, "w", encoding="utf-8") as out:
                                    out.write(line)
                                print(f"  Saved to {out_path}")
                                found_count += 1
            except Exception as e:
                pass
print("Done scanning.")
