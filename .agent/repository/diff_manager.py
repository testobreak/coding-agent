# repository/diff_manager.py
import difflib


class DiffManager:

    def generate_diff(
        self,
        old_content,
        new_content,
        path="file"
    ):

        diff = difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"{path}_old",
            tofile=f"{path}_new",
            lineterm=""
        )

        return "\n".join(diff)
