with open(r"d:\HRMS\.agent\retrieval\hybrid_ranker.py", "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if '"""' in line or "'''" in line:
            print(f"Line {idx+1}: {line.strip()}")
