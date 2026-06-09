src = open(r'd:\HRMS\.agent\planning\planner.py', encoding='utf-8').read()

# Replace retrieve target=state.goal with target=self._retrieve_query(state) in all plans
# There are several occurrences — do them all
old_target = 'target=state.goal,'
new_target = 'target=self._retrieve_query(state),'

count = src.count(old_target)
src = src.replace(old_target, new_target)
open(r'd:\HRMS\.agent\planning\planner.py', 'w', encoding='utf-8').write(src)
print(f'replaced {count} occurrences of retrieve target')
