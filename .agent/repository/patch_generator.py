# repository/patch_generator.py
from editing.patch import FilePatch, PatchSet, PatchType, PatchFormatter

class PatchGenerator:
    def generate(
        self,
        original_content: str,
        modified_content: str,
        path: str
    ) -> str:
        patch = FilePatch(
            file_path=path,
            patch_type=PatchType.REPLACE,
            start_line=1,
            end_line=max(1, len(original_content.splitlines())),
            old_text=original_content,
            new_text=modified_content
        )
        return PatchFormatter.to_unified_diff(PatchSet(patches=[patch]))
