# patch_manager.py

import subprocess
from pathlib import Path
import tempfile


class PatchManager:

    def __init__(self, root="."):

        self.root = Path(root)

    def apply_patch(self, patch_text):

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".patch",
            delete=False,
            encoding="utf-8"
        ) as f:

            f.write(patch_text)

            patch_file = f.name

        result = subprocess.run(
            ["git", "apply", patch_file],
            cwd=self.root,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:

            return {
                "success": False,
                "error": result.stderr
            }

        return {
            "success": True
        }
