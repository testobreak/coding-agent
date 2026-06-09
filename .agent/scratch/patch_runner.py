src = open(r'd:\HRMS\.agent\execution\test_runner.py', encoding='utf-8').read()

# Add test_filter parameter and mvn command building
old_sig = 'def run_backend_tests(self):'
new_sig = 'def run_backend_tests(self, test_filter=None):'

old_cmd = '        result = self._run_command(\n            ["mvn", "test", "-q", "--no-transfer-progress"],\n            backend_root,\n        )'
new_cmd = '        cmd = ["mvn", "test", "-q", "--no-transfer-progress"]\n        if test_filter:\n            cmd.append(f"-Dtest={test_filter}")\n            print(f"[TestRunner] Targeted test run: {test_filter}")\n        result = self._run_command(cmd, backend_root)'

if old_sig in src:
    src = src.replace(old_sig, new_sig, 1)
    print('sig replaced')
else:
    print('sig not found')

if old_cmd in src:
    src = src.replace(old_cmd, new_cmd, 1)
    print('cmd replaced')
else:
    print('cmd not found, trying to find it')
    import re
    m = re.search(r'result = self\._run_command\(\s*\[.mvn..*?\],\s*backend_root', src, re.DOTALL)
    if m:
        print('Found:', repr(m.group()[:100]))
    else:
        print('not found at all')

open(r'd:\HRMS\.agent\execution\test_runner.py', 'w', encoding='utf-8').write(src)
print('done')
