# editing/diff_ux.py
"""
DiffUX: Service to generate unified diffs for patches and (later) present them to the user.
Currently it generates the diff strings and prints them. Future integration will hook
into the UI layer (HTML/JS) or use the `ask_question` tool for approval.
"""

import difflib
from typing import Dict, List


class DiffUX:
    """Utility for handling diff generation and user approval.

    The workflow intended:
    1. Receive a PatchPlan and the original file contents.
    2. Generate a unified diff for each affected file.
    3. Present the diffs to the user (UI or console) and obtain approval.
    4. Return a boolean indicating whether all diffs were accepted.

    For now step 3 is a stub that logs the diff and auto‑approves.
    """

    @staticmethod
    def _unified_diff(original: str, modified: str, file_path: str) -> str:
        """Return a unified diff string for *original* vs *modified*.
        The diff includes file headers and uses ``@@`` hunk markers.
        """
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
        return "\n".join(diff)

    def generate_diffs(self, original_contents: Dict[str, str], modified_contents: Dict[str, str]) -> Dict[str, str]:
        """Generate diffs for each file present in *modified_contents*.

        Parameters
        ----------
        original_contents: dict mapping file path -> original text.
        modified_contents: dict mapping file path -> modified text.

        Returns
        -------
        dict mapping file path -> unified diff string.
        """
        diffs: Dict[str, str] = {}
        for path, new_content in modified_contents.items():
            old_content = original_contents.get(path, "")
            diffs[path] = self._unified_diff(old_content, new_content, path)
        return diffs

    def approve_diffs(self, diffs: Dict[str, str]) -> bool:
        """Placeholder for user approval.
        Currently logs diffs and auto‑approves. Future implementation will invoke
        the UI or use the `ask_question` tool.
        """
        for path, diff in diffs.items():
            print(f"[DiffUX] Diff for {path}:\n{diff}\n{'-'*40}\n")
            
        # Emit user_accepted event
        try:
            from context.session_cache import SessionCache
            from observability.event_bus import EventBus
            session = SessionCache.get_session("default")
            req_id = session.task_id or "unknown"
            
            EventBus().emit(
                event_type="user_accepted",
                request_id=req_id,
                payload={"accepted": True}
            )
        except Exception:
            pass
            
        return True
