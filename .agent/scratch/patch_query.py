src = open(r'd:\HRMS\.agent\planning\planner.py', encoding='utf-8').read()

# Replace the RETRIEVE action target in all plans to use suggested_queries
# The planner already passes state.goal as target — we need to add a helper
# that returns the best query (LLM suggested or goal)

# Add helper method before classify_task
helper = '''
    def _retrieve_query(self, state) -> str:
        """
        Return the best retrieval query for this state.
        Uses LLM suggested_queries if available, otherwise goal.
        """
        queries = getattr(state, "suggested_queries", []) or []
        if queries:
            return " | ".join(queries[:2])
        return state.goal

'''

insert_before = '    def classify_task('
if 'def _retrieve_query' not in src:
    src = src.replace(insert_before, helper + insert_before, 1)
    open(r'd:\HRMS\.agent\planning\planner.py', 'w', encoding='utf-8').write(src)
    print('helper added')
else:
    print('helper already present')
