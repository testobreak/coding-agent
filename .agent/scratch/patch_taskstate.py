src = open(r'd:\HRMS\.agent\memory\task_state.py', encoding='utf-8').read()

# Insert task_type and suggested_queries into the PLANNING section
old = (
    '    # =====================================================\r\n'
    '    # PLANNING\r\n'
    '    # =====================================================\r\n'
    '\r\n'
    '    current_plan: List[\r\n'
)
new = (
    '    # =====================================================\r\n'
    '    # PLANNING\r\n'
    '    # =====================================================\r\n'
    '\r\n'
    '    # Set by LLMPlanner: "bug_fix" | "feature" | "refactor" | "analysis"\r\n'
    '    task_type: Optional[str] = None\r\n'
    '\r\n'
    '    # Suggested search queries from LLMPlanner\r\n'
    '    suggested_queries: List[str] = field(\r\n'
    '        default_factory=list\r\n'
    '    )\r\n'
    '\r\n'
    '    current_plan: List[\r\n'
)

if old in src:
    src = src.replace(old, new, 1)
    open(r'd:\HRMS\.agent\memory\task_state.py', 'w', encoding='utf-8').write(src)
    print('fields added')
else:
    old_lf = old.replace('\r\n', '\n')
    new_lf = new.replace('\r\n', '\n')
    if old_lf in src:
        src = src.replace(old_lf, new_lf, 1)
        open(r'd:\HRMS\.agent\memory\task_state.py', 'w', encoding='utf-8').write(src)
        print('fields added (LF)')
    else:
        print('NOT FOUND')
