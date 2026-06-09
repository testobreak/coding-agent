import json

path = r"C:\Users\ashish\.gemini\antigravity\brain\54401983-f151-451e-b431-c3041d907ed3\.system_generated\logs\transcript.jsonl"
step_target = 3122

with open(path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            if data.get("step_index") == step_target:
                print(json.dumps(data, indent=2))
                break
        except Exception as e:
            pass
