# repository/patch_generator.py

from difflib import unified_diff


class PatchGenerator:

    def generate(
        self,
        original_content: str,
        modified_content: str,
        path: str
    ) -> str:

        diff = unified_diff(
            original_content.splitlines(),
            modified_content.splitlines(),
            fromfile=path,
            tofile=path,
            lineterm=""
        )

        return "\n".join(diff)
