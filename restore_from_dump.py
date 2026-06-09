import re
from pathlib import Path

dump_path = Path("agent_dump.md")
dest_root = Path(".agent")

def restore():
    try:
        content = dump_path.read_text(encoding="utf-16")
        print("Read agent_dump.md successfully with UTF-16 encoding.")
    except Exception as e:
        print(f"UTF-16 read failed: {e}. Trying UTF-8...")
        content = dump_path.read_text(encoding="utf-8", errors="ignore")

    # Split by the separator line
    sections = re.split(r"={100,}\r?\n", content)

    i = 1
    files_restored = 0
    while i < len(sections):
        path_sec = sections[i].strip()
        if not path_sec.startswith("PATH:"):
            i += 1
            continue
        
        # Extract path
        rel_path_str = path_sec.replace("PATH:", "").strip()
        rel_path_str = rel_path_str.replace("\\", "/")
        
        if i + 1 < len(sections):
            code_sec = sections[i+1].strip()
            code_lines = code_sec.split("\n")
            if code_lines[0].startswith("```"):
                actual_code_lines = code_lines[1:-1]
                actual_code = "\n".join(actual_code_lines)
            else:
                actual_code = code_sec
            
            target_path = dest_root / rel_path_str
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(actual_code + "\n", encoding="utf-8")
            print(f"Restored: {target_path} ({len(actual_code)} chars)")
            files_restored += 1
            i += 2
        else:
            i += 1

    print(f"Restoration complete. Restored {files_restored} files.")


if __name__ == "__main__":
    restore()

