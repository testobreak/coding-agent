# editing/patch_applier.py
#
# Parses and applies SEARCH/REPLACE blocks or complete symbol replacements to file content.

import re
from editing.ast_locator import ASTNodeInfo

class PatchApplier:
    def apply(self, file_content: str, patch_str: str, symbol_info: ASTNodeInfo = None) -> str:
        # If symbol_info is provided and is a valid AST node (not fallback), perform surgical byte-level replacement
        if symbol_info and symbol_info.node_type != "fallback":
            try:
                # 1. Apply the patch strictly within the isolated symbol content
                new_symbol_content = self.apply(symbol_info.content, patch_str, symbol_info=None)
                
                # 2. Surgically replace the original symbol's byte range in file content
                file_bytes = file_content.encode("utf-8")
                new_symbol_bytes = new_symbol_content.encode("utf-8")
                
                # Verify that the byte offsets correspond to the expected symbol content
                original_bytes = file_bytes[symbol_info.start_byte:symbol_info.end_byte]
                expected_bytes = symbol_info.content.encode("utf-8")
                
                if original_bytes == expected_bytes:
                    modified_bytes = file_bytes[:symbol_info.start_byte] + new_symbol_bytes + file_bytes[symbol_info.end_byte:]
                    return modified_bytes.decode("utf-8", errors="replace")
                else:
                    print(f"[PatchApplier] Byte mismatch at [{symbol_info.start_byte}:{symbol_info.end_byte}]. "
                          f"Expected: {expected_bytes!r}, Got: {original_bytes!r}. Falling back to string replacement.")
            except Exception as e:
                print(f"[PatchApplier] Byte-level replacement failed: {e}. Falling back to string replacement.")

        # Check if we have SEARCH/REPLACE block format
        if "<<<<<<< SEARCH" in patch_str:
            parts = patch_str.split("<<<<<<< SEARCH")
            result = file_content
            for part in parts[1:]:
                if "=======" not in part or ">>>>>>> REPLACE" not in part:
                    continue
                sub_parts = part.split("=======")
                search_content = sub_parts[0]
                # Keep original trailing newlines but strip wrapping marker artifacts
                if search_content.startswith("\r\n"):
                    search_content = search_content[2:]
                elif search_content.startswith("\n"):
                    search_content = search_content[1:]
                
                replace_part = sub_parts[1].split(">>>>>>> REPLACE")[0]
                if replace_part.startswith("\r\n"):
                    replace_part = replace_part[2:]
                elif replace_part.startswith("\n"):
                    replace_part = replace_part[1:]
                
                # Strip trailing marker carriage returns
                if search_content.endswith("\r\n"):
                    search_content = search_content[:-2]
                elif search_content.endswith("\n"):
                    search_content = search_content[:-1]
                if replace_part.endswith("\r\n"):
                    replace_part = replace_part[:-2]
                elif replace_part.endswith("\n"):
                    replace_part = replace_part[:-1]

                # Match and replace in file
                if search_content in result:
                    result = result.replace(search_content, replace_part, 1)
                else:
                    # Fallback to normalized comparison (spacing/bracing ignored) if exact match fails
                    norm_search = self._normalize(search_content)
                    if not norm_search:
                        raise ValueError(f"Empty search block in patch")
                    
                    # Search line by line or do a fuzzy search
                    # For safety, raise a clear error so that transaction engine can roll back
                    raise ValueError(f"Could not find exact search block in file content:\n{search_content}")
            return result
        else:
            # Fallback: treat the LLM output as a complete replacement of the symbol's content
            if symbol_info:
                clean_patch = self._clean_markdown(patch_str)
                if symbol_info.content in file_content:
                    return file_content.replace(symbol_info.content, clean_patch, 1)
                else:
                    # Try fallback to normalize match or line-range bounds
                    lines = file_content.splitlines()
                    # 1-indexed lines
                    start_idx = symbol_info.start_line - 1
                    end_idx = symbol_info.end_line
                    # Reconstruct lines with replacement
                    lines[start_idx:end_idx] = clean_patch.splitlines()
                    return "\n".join(lines)
            else:
                raise ValueError("Failed to apply patch: No SEARCH/REPLACE block and symbol information not found.")

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", "", text)

    def _clean_markdown(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        return text
