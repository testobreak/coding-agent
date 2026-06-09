import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'd:\HRMS\.agent')
os.chdir(r'd:\HRMS\.agent')

modules = [
    'db.connection',
    'parsers.base',
    'parsers.java_parser',
    'parsers.python_parser',
    'parsers.js_parser',
    'parsers.ts_parser',
    'parsers.registry',
    'repository.scanner',
    'indexing.symbol_indexer',
]
errors = []
for mod in modules:
    try:
        __import__(mod)
        print(f'  OK  {mod}')
    except Exception as e:
        print(f'  ERR {mod}: {e}')
        errors.append(mod)

print()
print('RESULT:', 'ALL CLEAN' if not errors else f'FAILED: {errors}')
