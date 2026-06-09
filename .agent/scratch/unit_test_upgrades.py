import sys, os, io, contextlib
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'd:\HRMS\.agent')
os.chdir(r'd:\HRMS\.agent')

print('=== Unit tests (no indexing) ===')
print()

# 1. LLMPlanner parse - valid JSON
from llm.llm_planner import LLMPlanner
lp = LLMPlanner.__new__(LLMPlanner)
lp.llm = None

good = '{"task_type":"bug_fix","reasoning":"fix keyword","diagnosis":"null check missing","target_files":["EmployeeService.java"],"suggested_queries":["calculateSalary","deduction"]}'
r = lp._parse_response(good)
assert r['task_type'] == 'bug_fix', r
assert 'calculateSalary' in r['suggested_queries']
assert r['target_files'] == ['EmployeeService.java']
print('  OK  LLMPlanner._parse_response() valid JSON')

# 2. Markdown fences stripped
fenced = '```json\n{"task_type":"feature","reasoning":"add","diagnosis":"no endpoint","target_files":[],"suggested_queries":["leave"]}\n```'
r2 = lp._parse_response(fenced)
assert r2['task_type'] == 'feature'
print('  OK  LLMPlanner._parse_response() markdown fences stripped')

# 3. Invalid response -> None
r3 = lp._parse_response('sorry, I cannot answer that')
assert r3 is None
print('  OK  LLMPlanner._parse_response() None on bad JSON')

# 4. Unknown task_type normalised to analysis
r4 = lp._parse_response('{"task_type":"weird","diagnosis":"x","target_files":[],"suggested_queries":[]}')
assert r4['task_type'] == 'analysis'
print('  OK  LLMPlanner._parse_response() unknown type -> analysis')

# 5. DiffPrinter - basic diff
from runtime.diff_printer import DiffPrinter
dp = DiffPrinter()

orig = 'def calc():\n    return a - b\n'
mod  = 'def calc():\n    return a - (b or 0)\n'
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    dp.print_diff(orig, mod, 'calc.py', success=True)
out = buf.getvalue()
assert 'PATCH APPLIED' in out, 'missing PATCH APPLIED'
assert 'changed' in out, 'missing summary line'
print('  OK  DiffPrinter.print_diff() success case')

# 6. DiffPrinter - rollback
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    dp.print_diff(orig, mod, 'calc.py', success=False)
assert 'ROLLED BACK' in buf2.getvalue()
print('  OK  DiffPrinter.print_diff() rollback case')

# 7. DiffPrinter - no change
buf3 = io.StringIO()
with contextlib.redirect_stdout(buf3):
    dp.print_diff(orig, orig, 'calc.py', success=True)
assert 'no changes' in buf3.getvalue()
print('  OK  DiffPrinter.print_diff() no-change case')

# 8. DiagnosticsReporter
from runtime.diagnostics import DiagnosticsReporter
dr = DiagnosticsReporter()
plan = {
    'task_type': 'bug_fix',
    'reasoning': 'test reason',
    'diagnosis': 'The method is missing a null check on deductions.',
    'target_files': ['EmployeeService.java', 'SalaryController.java'],
    'suggested_queries': ['calculateSalary', 'salary null'],
}
buf4 = io.StringIO()
with contextlib.redirect_stdout(buf4):
    dr.report('fix salary bug', plan, [])
out4 = buf4.getvalue()
assert 'AGENT DIAGNOSIS' in out4
assert 'BUG_FIX' in out4
assert 'EmployeeService.java' in out4
assert 'calculateSalary' in out4
assert 'null check' in out4
print('  OK  DiagnosticsReporter.report() full output')

# 9. announce_step
buf5 = io.StringIO()
with contextlib.redirect_stdout(buf5):
    dr.announce_step('modify_file', 'EmployeeService.java')
assert 'modify_file' in buf5.getvalue()
print('  OK  DiagnosticsReporter.announce_step()')

# 10. TaskState new fields
from memory.task_state import TaskState
ts = TaskState(goal='test')
assert hasattr(ts, 'task_type')
assert hasattr(ts, 'suggested_queries')
assert ts.task_type is None
assert ts.suggested_queries == []
ts.task_type = 'bug_fix'
ts.suggested_queries = ['salary', 'deduction']
assert ts.task_type == 'bug_fix'
print('  OK  TaskState.task_type + suggested_queries fields')

# 11. Planner uses LLM task_type
from planning.planner import Planner
p = Planner()
ts2 = TaskState(goal='do something unrecognised')
ts2.task_type = 'feature'
actions = p.create_plan(ts2)
action_types = [str(a.action_type if hasattr(a, 'action_type') else a.get('action_type','')) for a in actions]
print(f'  action_types for feature task: {action_types}')
assert any('retrieve' in t.lower() or 'modify' in t.lower() for t in action_types), \
    f'Expected feature actions, got: {action_types}'
print('  OK  Planner uses LLM task_type from state')

print()
print('ALL 11 UNIT TESTS PASSED')
