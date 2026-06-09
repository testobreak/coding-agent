import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'd:\HRMS\.agent')

from tree_sitter import Language, Parser

import tree_sitter_java as ts_java
import tree_sitter_python as ts_python
import tree_sitter_javascript as ts_js
import tree_sitter_typescript as ts_ts

print('Testing Language init patterns...')

raw = ts_java.language()
print(f'ts_java.language() type: {type(raw).__name__}')

# 0.21 style
try:
    l = Language(raw, 'java')
    print('Pattern (raw, name): OK')
except TypeError as e:
    print(f'Pattern (raw, name): FAIL - {e}')

# 0.22+ style - Language takes ptr directly
try:
    l = Language(raw)
    print('Pattern (raw,): OK')
except TypeError as e:
    print(f'Pattern (raw,): FAIL - {e}')

# Check if there is a ptr attribute
if hasattr(raw, 'ptr'):
    try:
        l = Language(raw.ptr, 'java')
        print('Pattern (raw.ptr, name): OK')
    except Exception as e:
        print(f'Pattern (raw.ptr, name): FAIL - {e}')

# Try ctypes.addressof
try:
    import ctypes
    ptr = ctypes.cast(raw, ctypes.c_void_p).value
    l = Language(ptr, 'java')
    print('Pattern (ctypes ptr, name): OK')
except Exception as e:
    print(f'Pattern (ctypes ptr, name): FAIL - {e}')

# Try with the language ID method from 0.22
try:
    l = Language(ts_java.language_java())
    print('Pattern language_java(): OK')
except Exception as e:
    print(f'Pattern language_java(): FAIL - {e}')

# Check what methods ts_java has
print('ts_java attrs:', [a for a in dir(ts_java) if not a.startswith('_')])
