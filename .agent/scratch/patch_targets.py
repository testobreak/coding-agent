src = open(r'd:\HRMS\.agent\planning\planner.py', encoding='utf-8').read()

# Find and replace resolve_target_files to prioritise LLM targets
old = '''    def resolve_target_files(
        self,
        state: TaskState
    ) -> List[str]:

        #
        # Highest confidence source
        #

        if getattr(
            state,
            "modification_targets",
            None
        ):

            return list(
                dict.fromkeys(
                    state.modification_targets
                )
            )[:5]

        #
        # Fallback to retrieved chunks
        #

        files = []

        for chunk in getattr(
            state,
            "retrieved_chunks",
            []
        ):

            path = chunk.get("file")

            if (
                path
                and path not in files
            ):
                files.append(path)

        if files:

            return files[:5]

        #
        # Last resort:
        # use repository root context
        #

        return []'''

new = '''    def resolve_target_files(
        self,
        state: TaskState
    ) -> List[str]:

        # Priority 1: test failure targets (parser-resolved, highest confidence)
        failure_targets = list(getattr(state, "test_failure_targets", []) or [])
        if failure_targets:
            return failure_targets[:5]

        # Priority 2: modification_targets (set by LLMPlanner or FailureAnalysisEngine)
        if getattr(state, "modification_targets", None):
            return list(dict.fromkeys(state.modification_targets))[:5]

        # Priority 3: TargetRanker multi-signal ranking
        try:
            from execution.target_ranker import TargetRanker
            ranked = TargetRanker().top_targets(state, n=5)
            if ranked:
                return ranked
        except Exception:
            pass

        # Priority 4: retrieved chunks
        files = []
        for chunk in getattr(state, "retrieved_chunks", []):
            path = chunk.get("file")
            if path and path not in files:
                files.append(path)
        if files:
            return files[:5]

        return []'''

if old in src:
    src = src.replace(old, new, 1)
    open(r'd:\HRMS\.agent\planning\planner.py', 'w', encoding='utf-8').write(src)
    print('resolve_target_files patched')
else:
    # Try normalised
    import re
    # Just check it's there at all
    if 'def resolve_target_files' in src:
        print('method exists but pattern mismatch — manual check needed')
    else:
        print('method not found at all')
