src = open(r'd:\HRMS\.agent\scratch\probe_ts.py', encoding='utf-8').read()  # throwaway

import os, re

files = [
    r'd:\HRMS\.agent\parsers\java_parser.py',
    r'd:\HRMS\.agent\parsers\python_parser.py',
    r'd:\HRMS\.agent\parsers\js_parser.py',
    r'd:\HRMS\.agent\parsers\ts_parser.py',
]

# Pattern: Language(ts_xxx.language(), "langname")  -> Language(ts_xxx.language())
pattern = re.compile(r'Language\(([^,)]+\.language\(\)),\s*"[^"]+"\)')

for path in files:
    text = open(path, encoding='utf-8').read()
    new_text, count = pattern.subn(r'Language(\1)', text)
    if count:
        open(path, 'w', encoding='utf-8').write(new_text)
        print(f'  Fixed {count} occurrence(s) in {os.path.basename(path)}')
    else:
        print(f'  No changes in {os.path.basename(path)}')

# Also fix ts_parser: Language(ts_typescript.language_typescript()) 
# and Language(ts_typescript.language_tsx()) — these have no second arg already
# but they use language_typescript() / language_tsx() — need to check
ts_src = open(r'd:\HRMS\.agent\parsers\ts_parser.py', encoding='utf-8').read()
print()
print('ts_parser Language lines:')
for line in ts_src.splitlines():
    if 'Language(' in line:
        print(' ', line.strip())
