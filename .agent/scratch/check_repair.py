import re, sys, os
sys.path.insert(0, r'd:\HRMS\.agent')
os.chdir(r'd:\HRMS\.agent')
src = open(r'd:\HRMS\.agent\execution\executor.py', encoding='utf-8').read()

# Does repair_from_context call set_last_modification?
if 'repair_from_context' in src:
    idx = src.index('repair_from_context')
    # find the dispatch block
    block = src[idx:idx+2000]
    has_setmod = 'set_last_modification' in block
    print(f'repair_from_context found, has set_last_modification: {has_setmod}')
    # Count occurrences of set_last_modification in whole file
    count = src.count('set_last_modification')
    print(f'Total set_last_modification calls: {count}')
else:
    print('repair_from_context not found')
