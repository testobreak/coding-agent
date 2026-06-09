src = open(r'd:\HRMS\.agent\execution\executor.py', encoding='utf-8').read()

old = (
    '        elif tool == "run_backend_tests":\n\n'
    '            result = self.tests.run_backend_tests()\n'
    '            self._handle_test_failures(result)\n'
    '            return result'
)

new = (
    '        elif tool == "run_backend_tests":\n\n'
    '            # Use impact analysis for targeted test runs when possible\n'
    '            test_filter = None\n'
    '            state = self.state_manager.get_state()\n'
    '            modified_files = list(getattr(state, "modified_files", []) or [])\n'
    '            if modified_files:\n'
    '                last_modified = modified_files[-1]\n'
    '                try:\n'
    '                    dep_graph = getattr(self.retriever, "dependency_graph", None)\n'
    '                    if dep_graph and dep_graph._built:\n'
    '                        self.impact_analyzer.graph = dep_graph\n'
    '                    impact = self.impact_analyzer.analyze(last_modified)\n'
    '                    test_filter = impact.get("test_filter")\n'
    '                    if test_filter:\n'
    '                        print(f"[ImpactAnalyzer] Targeted tests: {test_filter}")\n'
    '                except Exception as e:\n'
    '                    print(f"[ImpactAnalyzer] Error: {e}")\n'
    '            result = self.tests.run_backend_tests(test_filter=test_filter)\n'
    '            self._handle_test_failures(result)\n'
    '            return result'
)

if old in src:
    src = src.replace(old, new, 1)
    open(r'd:\HRMS\.agent\execution\executor.py', 'w', encoding='utf-8').write(src)
    print('done')
else:
    print('NOT FOUND')
    import re
    m = re.search(r'elif tool == "run_backend_tests".*?return result', src, re.DOTALL)
    if m:
        print('Found block:', repr(m.group()[:300]))
