src = open(r'd:\HRMS\.agent\planning\planner.py', encoding='utf-8').read()

old = (
    '    def create_plan(\r\n'
    '        self,\r\n'
    '        state: TaskState\r\n'
    '    ) -> List[Action]:\r\n'
    '\r\n'
    '        goal = state.goal.lower()\r\n'
    '\r\n'
    '        task_type = self.classify_task(\r\n'
    '            goal\r\n'
    '        )\r\n'
)

new = (
    '    def create_plan(\r\n'
    '        self,\r\n'
    '        state: TaskState\r\n'
    '    ) -> List[Action]:\r\n'
    '\r\n'
    '        goal = state.goal.lower()\r\n'
    '\r\n'
    '        # Prefer task_type set by LLMPlanner; fall back to keywords.\r\n'
    '        llm_task_type = getattr(state, "task_type", None)\r\n'
    '        _type_map = {\r\n'
    '            "bug_fix":  BUG_FIX,\r\n'
    '            "feature":  FEATURE,\r\n'
    '            "refactor": REFACTOR,\r\n'
    '            "analysis": ANALYSIS,\r\n'
    '        }\r\n'
    '        if llm_task_type and llm_task_type in _type_map:\r\n'
    '            task_type = _type_map[llm_task_type]\r\n'
    '        else:\r\n'
    '            task_type = self.classify_task(goal)\r\n'
)

if old in src:
    src = src.replace(old, new, 1)
    open(r'd:\HRMS\.agent\planning\planner.py', 'w', encoding='utf-8').write(src)
    print('patched')
else:
    print('NOT FOUND — checking line endings')
    # Try LF
    old_lf = old.replace('\r\n', '\n')
    if old_lf in src:
        new_lf = new.replace('\r\n', '\n')
        src = src.replace(old_lf, new_lf, 1)
        open(r'd:\HRMS\.agent\planning\planner.py', 'w', encoding='utf-8').write(src)
        print('patched (LF)')
    else:
        print('still not found')
