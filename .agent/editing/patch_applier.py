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

    def apply_operation(self, content: str, op_type: str, replacement: str, span: ASTNodeInfo) -> str:
        """Apply a structured patch operation (replace, insert_before, insert_after, delete, rename_symbol)
        surgically at the byte level within the file content, falling back to line-level if byte offsets mismatch.
        """
        # Encode content to bytes to handle multi-byte characters accurately
        content_bytes = content.encode("utf-8")
        
        # Verify if byte offsets match the expected span content
        byte_level_valid = False
        if (span.start_byte is not None and span.end_byte is not None and 
            0 <= span.start_byte <= len(content_bytes) and 0 <= span.end_byte <= len(content_bytes) and
            span.start_byte <= span.end_byte):
            
            original_bytes = content_bytes[span.start_byte:span.end_byte]
            expected_bytes = span.content.encode("utf-8")
            if original_bytes == expected_bytes or span.node_type == "fallback":
                byte_level_valid = True

        if byte_level_valid:
            try:
                if op_type == "replace":
                    new_bytes = replacement.encode("utf-8")
                    modified_bytes = content_bytes[:span.start_byte] + new_bytes + content_bytes[span.end_byte:]
                    return modified_bytes.decode("utf-8", errors="replace")
                
                elif op_type == "delete":
                    modified_bytes = content_bytes[:span.start_byte] + content_bytes[span.end_byte:]
                    return modified_bytes.decode("utf-8", errors="replace")
                
                elif op_type == "insert_before":
                    sep = b"\n" if not replacement.endswith("\n") else b""
                    new_bytes = replacement.encode("utf-8") + sep
                    modified_bytes = content_bytes[:span.start_byte] + new_bytes + content_bytes[span.start_byte:]
                    return modified_bytes.decode("utf-8", errors="replace")
                
                elif op_type == "insert_after":
                    is_newline_after = False
                    if span.end_byte < len(content_bytes):
                        if content_bytes[span.end_byte:span.end_byte+1] == b'\n':
                            is_newline_after = True
                    
                    new_bytes = replacement.encode("utf-8")
                    if is_newline_after:
                        insert_pos = span.end_byte + 1
                        sep = b"\n" if not replacement.endswith("\n") else b""
                        modified_bytes = content_bytes[:insert_pos] + new_bytes + sep + content_bytes[insert_pos:]
                    else:
                        sep = b"\n" if not replacement.startswith("\n") else b""
                        modified_bytes = content_bytes[:span.end_byte] + sep + new_bytes + content_bytes[span.end_byte:]
                    return modified_bytes.decode("utf-8", errors="replace")
                
                elif op_type == "rename_symbol":
                    short_name = span.name.split(".")[-1]
                    span_str = span.content
                    if short_name in span_str:
                        lines = span_str.splitlines()
                        if lines:
                            first_line = lines[0]
                            if short_name in first_line:
                                new_first_line = first_line.replace(short_name, replacement, 1)
                                lines[0] = new_first_line
                                new_span_str = "\n".join(lines)
                                new_bytes = new_span_str.encode("utf-8")
                                modified_bytes = content_bytes[:span.start_byte] + new_bytes + content_bytes[span.end_byte:]
                                return modified_bytes.decode("utf-8", errors="replace")
            except Exception as e:
                print(f"[PatchApplier] apply_operation byte-level failed: {e}. Falling back to line-level.")

        # Fallback: Line-level edits
        lines = content.splitlines()
        start_idx = max(0, min(len(lines) - 1, span.start_line - 1))
        end_idx = max(start_idx, min(len(lines) - 1, span.end_line - 1))
        
        if op_type == "replace":
            lines[start_idx : end_idx + 1] = replacement.splitlines()
        elif op_type == "delete":
            del lines[start_idx : end_idx + 1]
        elif op_type == "insert_before":
            lines[start_idx : start_idx] = replacement.splitlines()
        elif op_type == "insert_after":
            lines[end_idx + 1 : end_idx + 1] = replacement.splitlines()
        elif op_type == "rename_symbol":
            short_name = span.name.split(".")[-1]
            first_line = lines[start_idx]
            if short_name in first_line:
                lines[start_idx] = first_line.replace(short_name, replacement, 1)
                
        return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


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

    def apply_span_patch(self, file_content: str, patch_str: str, symbol_info = None) -> str:
        clean_patch = self._clean_markdown(patch_str)
        if not symbol_info:
            return clean_patch

        # Clean SEARCH/REPLACE format inside the target AST span
        if "<<<<<<< SEARCH" in clean_patch:
            try:
                new_symbol_content = self.apply(symbol_info.content, clean_patch, symbol_info=None)
                new_symbol_bytes = new_symbol_content.encode("utf-8")
                
                file_bytes = file_content.encode("utf-8")
                original_bytes = file_bytes[symbol_info.start_byte:symbol_info.end_byte]
                expected_bytes = symbol_info.content.encode("utf-8")
                if original_bytes == expected_bytes:
                    modified_bytes = file_bytes[:symbol_info.start_byte] + new_symbol_bytes + file_bytes[symbol_info.end_byte:]
                    return modified_bytes.decode("utf-8", errors="replace")
            except Exception as e:
                print(f"[PatchApplier] apply_span_patch SEARCH/REPLACE failed: {e}")

        # Fallback to full replacement of the symbol's byte range
        try:
            file_bytes = file_content.encode("utf-8")
            original_bytes = file_bytes[symbol_info.start_byte:symbol_info.end_byte]
            expected_bytes = symbol_info.content.encode("utf-8")
            new_symbol_bytes = clean_patch.encode("utf-8")
            if original_bytes == expected_bytes:
                modified_bytes = file_bytes[:symbol_info.start_byte] + new_symbol_bytes + file_bytes[symbol_info.end_byte:]
                return modified_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[PatchApplier] apply_span_patch byte replacement failed: {e}")

        if symbol_info.content in file_content:
            return file_content.replace(symbol_info.content, clean_patch, 1)

        return file_content

    def insert_import(self, file_content: str, import_statement: str, language: str = "java") -> str:
        lines = file_content.splitlines()
        import_stmt = import_statement.strip()
        if import_stmt in file_content:
            return file_content

        import_index = -1
        package_index = -1
        for idx, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped.startswith("import ") or line_stripped.startswith("import {") or (language == "python" and line_stripped.startswith("from ")):
                import_index = idx
            elif line_stripped.startswith("package "):
                package_index = idx

        if import_index != -1:
            lines.insert(import_index + 1, import_stmt)
        elif package_index != -1:
            lines.insert(package_index + 1, "")
            lines.insert(package_index + 2, import_stmt)
        else:
            lines.insert(0, import_stmt)
            lines.insert(1, "")

        return "\n".join(lines) + ("\n" if file_content.endswith("\n") else "")

    def insert_class_member(self, file_content: str, class_name: str, member_content: str, language: str = "java") -> str:
        if language == "python":
            lines = file_content.splitlines()
            class_idx = -1
            for idx, line in enumerate(lines):
                if line.strip().startswith(f"class {class_name}"):
                    class_idx = idx
                    break
            if class_idx == -1:
                return file_content

            class_line = lines[class_idx]
            base_indent = len(class_line) - len(class_line.lstrip())
            insert_idx = len(lines)
            for idx in range(class_idx + 1, len(lines)):
                line = lines[idx]
                if line.strip():
                    line_indent = len(line) - len(line.lstrip())
                    if line_indent <= base_indent:
                        insert_idx = idx
                        break

            indented_member = []
            for line in member_content.splitlines():
                indented_member.append("    " * (base_indent // 4 + 1) + line)
            lines.insert(insert_idx, "")
            for line in reversed(indented_member):
                lines.insert(insert_idx, line)
            return "\n".join(lines) + ("\n" if file_content.endswith("\n") else "")

        pattern = r"\bclass\s+" + re.escape(class_name) + r"\b"
        match = re.search(pattern, file_content)
        if not match:
            return file_content

        start_idx = match.start()
        open_brace_idx = file_content.find("{", start_idx)
        if open_brace_idx == -1:
            return file_content

        depth = 1
        close_brace_idx = -1
        for idx in range(open_brace_idx + 1, len(file_content)):
            char = file_content[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    close_brace_idx = idx
                    break

        if close_brace_idx == -1:
            return file_content

        last_newline = file_content.rfind("\n", 0, close_brace_idx)
        indent = ""
        if last_newline != -1:
            indent = file_content[last_newline + 1:close_brace_idx]

        formatted_member = "\n"
        for line in member_content.splitlines():
            formatted_member += indent + "    " + line + "\n"
        formatted_member += indent

        new_content = file_content[:close_brace_idx] + formatted_member + file_content[close_brace_idx:]
        return new_content

