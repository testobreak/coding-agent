import os
import json
import re

brain_dir = r"C:\Users\ashish\.gemini\antigravity\brain"
target_file_name = "verify_transaction.py"

print("Searching transcripts for write_to_file/replace_file_content calls...")
for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file == "transcript.jsonl":
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for idx, line in enumerate(f):
                        if "write_to_file" in line and target_file_name in line:
                            try:
                                data = json.loads(line)
                                # Check tool calls
                                for tc in data.get("tool_calls", []):
                                    if tc.get("name") == "default_api:write_to_file":
                                        args = tc.get("arguments", {})
                                        tgt = args.get("TargetFile", "")
                                        if target_file_name in tgt:
                                            content = args.get("CodeContent", "")
                                            if content:
                                                print(f"Found write_to_file in {path} at step {data.get('step_index') or idx}")
                                                out_path = f"write_verify_tx_{data.get('step_index') or idx}.txt"
                                                with open(out_path, "w", encoding="utf-8") as out:
                                                    out.write(content)
                                                print(f"  Saved code content to {out_path}")
                            except Exception as e:
                                pass
            except Exception as e:
                pass
print("Done searching.")
