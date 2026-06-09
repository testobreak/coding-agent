import re, sys, os
sys.path.insert(0, r'd:\HRMS\.agent')
os.chdir(r'd:\HRMS\.agent')

src = open(r'd:\HRMS\.agent\execution\executor.py', encoding='utf-8').read()

# Find the modify_file block — enrich set_last_modification with original/modified
# Current: self.state_manager.set_last_modification(result)
# We want:
#   self.state_manager.set_last_modification({
#       **result,
#       "original": modification_result.get("original", ""),
#       "modified": modification_result.get("modified", ""),
#   })

old = (
    '            self.state_manager.set_last_modification(\n'
    '                result\n'
    '            )\n'
)
new = (
    '            self.state_manager.set_last_modification({\n'
    '                **(result or {}),\n'
    '                "original": modification_result.get("original", "") if isinstance(modification_result, dict) else "",\n'
    '                "modified": modification_result.get("modified", "") if isinstance(modification_result, dict) else "",\n'
    '            })\n'
)

if old in src:
    src = src.replace(old, new, 1)
    open(r'd:\HRMS\.agent\execution\executor.py', 'w', encoding='utf-8').write(src)
    print('patched')
else:
    # Try CRLF
    old_cr = old.replace('\n', '\r\n')
    new_cr = new.replace('\n', '\r\n')
    if old_cr in src:
        src = src.replace(old_cr, new_cr, 1)
        open(r'd:\HRMS\.agent\execution\executor.py', 'w', encoding='utf-8').write(src)
        print('patched (CRLF)')
    else:
        # Search for the pattern another way
        m = re.search(r'set_last_modification\(\s*result\s*\)', src)
        if m:
            src = src[:m.start()] + (
                'set_last_modification({\n'
                '                **(result or {}),\n'
                '                "original": modification_result.get("original", "") if isinstance(modification_result, dict) else "",\n'
                '                "modified": modification_result.get("modified", "") if isinstance(modification_result, dict) else "",\n'
                '            })'
            ) + src[m.end():]
            open(r'd:\HRMS\.agent\execution\executor.py', 'w', encoding='utf-8').write(src)
            print('patched (regex)')
        else:
            print('NOT FOUND')
