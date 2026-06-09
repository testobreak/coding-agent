import os
import json

brain_dir = r"C:\Users\ashish\.gemini\antigravity\brain"
print("Extracting write event contents...")

targets_to_extract = [
    ("hybrid_ranker.py", "hybrid_ranker"),
    ("verify_resolver.py", "verify_resolver"),
    ("verify_transaction.py", "verify_transaction")
]

for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file == "transcript.jsonl":
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f):
                        for name_raw, name_prefix in targets_to_extract:
                            if name_raw in line and ("write_to_file" in line or "replace_file_content" in line):
                                try:
                                    data = json.loads(line)
                                    tool_calls = data.get("tool_calls", [])
                                    for tc in tool_calls:
                                        name = tc.get("name", "")
                                        args = tc.get("args", {}) or tc.get("arguments", {})
                                        target_file = args.get("TargetFile", "") or args.get("TargetPath", "") or args.get("Target", "")
                                        
                                        if name_raw in str(target_file).lower():
                                            content = args.get("CodeContent", "") or args.get("ReplacementContent", "") or ""
                                            if len(content) > 0:
                                                step = data.get("step_index") or line_num
                                                out_fn = f"extract_{name_prefix}_step_{step}.txt"
                                                with open(out_fn, "w", encoding="utf-8") as out:
                                                    out.write(content)
                                                print(f"Saved {out_fn} (len={len(content)})")
                                except Exception as e:
                                    pass
            except Exception as e:
                pass
print("Done extracting.")
