src = open(r'd:\HRMS\.agent\execution\test_runner.py', encoding='utf-8').read()

# Check what the current method signature looks like
import re
m = re.search(r'def run_backend_tests\(.*?\):', src)
if m:
    print("Found:", m.group())
else:
    print("Not found")
    print(src[:500])
