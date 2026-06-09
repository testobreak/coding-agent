import os
import json

brain_dir = r"C:\Users\ashish\.gemini\antigravity\brain"
print("Scanning transcripts for specific target files...")

targets_to_find = [
    "hybrid_ranker.py",
    "verify_resolver.py",
    "verify_transaction.py"
]

write_events = []
for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file == "transcript.jsonl":
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f):
                        if any(t in line for t in targets_to_find):
                            if "write_to_file" in line or "replace_file_content" in line:
                                try:
                                    data = json.loads(line)
                                    tool_calls = data.get("tool_calls", [])
                                    for tc in tool_calls:
                                        name = tc.get("name", "")
                                        args = tc.get("args", {}) or tc.get("arguments", {})
                                        target_file = args.get("TargetFile", "") or args.get("TargetPath", "") or args.get("Target", "")
                                        
                                        if any(t in str(target_file).lower() for t in targets_to_find):
                                            content = args.get("CodeContent", "") or args.get("ReplacementContent", "") or ""
                                            write_events.append({
                                                "path": path,
                                                "line": line_num,
                                                "tool": name,
                                                "target": target_file,
                                                "content_len": len(content),
                                                "step_index": data.get("step_index")
                                            })
                                except Exception:
                                    pass
            except Exception as e:
                print(f"Error reading {path}: {e}")

print(f"Found {len(write_events)} write events:")
write_events.sort(key=lambda x: (str(x["target"]).lower(), x["step_index"] or 0))
for ev in write_events:
    print(f"Target: {ev['target']} | Len: {ev['content_len']} | Step: {ev['step_index']} | File: {ev['path']}")
