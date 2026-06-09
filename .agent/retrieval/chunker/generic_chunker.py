# retrieval/chunker/generic_chunker.py

import re
from pathlib import Path


class GenericChunker:

    def __init__(self):
        self.max_chunk_lines = 80
        self.chunk_overlap = 15

        # Regex patterns for various file types
        self.java_import_pattern = re.compile(r'^\s*import\s+([\w\.\*]+)\s*;')
        self.js_ts_import_pattern = re.compile(r'^\s*import\s+.*?from\s+[\'"]([^\'"]+)[\'"]')
        self.require_import_pattern = re.compile(r'(?:const|let|var)\s+.*?\s*=\s*require\([\'"]([^\'"]+)[\'"]\)')

        # Symbol detection patterns
        # Java patterns
        self.java_class_pattern = re.compile(r'(?:public|protected|private|static|\s)+class\s+(\w+)')
        self.java_interface_pattern = re.compile(r'(?:public|protected|private|\s)+interface\s+(\w+)')
        self.java_method_pattern = re.compile(r'(?:public|protected|private|static|\s)+(?:[\w<>\[\]\?]+)\s+(\w+)\s*\(')

        # JS / TS / TSX / JSX patterns
        self.js_class_pattern = re.compile(r'class\s+(\w+)')
        self.js_function_pattern = re.compile(r'function\s+(\w+)')
        self.js_arrow_fn_pattern = re.compile(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:\([^\)]*\)|[^=]+)\s*=>')
        self.js_export_default_pattern = re.compile(r'export\s+default\s+function\s+(\w+)?')
        self.js_export_const_pattern = re.compile(r'export\s+const\s+(\w+)')

    # =====================================================
    # MAIN ENTRY
    # =====================================================

    def chunk_file(self, file_path):
        path = Path(file_path)
        suffix = path.suffix.lower()

        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[Generic Chunker Error] {file_path}: {e}")
            return []

        lines = source.splitlines()
        if not lines:
            return []

        # 1. Extract Imports
        imports = self.extract_imports(lines, suffix)

        # 2. Extract Docstrings / Block Comments
        docstrings = self.extract_block_comments(source)

        # 3. Slide over file lines to build chunks
        chunks = []
        total_lines = len(lines)
        start = 0
        chunk_idx = 0

        # Precompute total chunks estimate
        total_chunks_est = max(1, (total_lines - self.chunk_overlap) // (self.max_chunk_lines - self.chunk_overlap) + 1)

        while start < total_lines:
            end = min(start + self.max_chunk_lines, total_lines)
            chunk_lines = lines[start:end]
            chunk_code = "\n".join(chunk_lines)

            # Find matching symbols and docstrings inside this range
            symbol_name, symbol_type = self.detect_symbol(chunk_lines, suffix, path.stem)
            docstring = self.find_relevant_docstring(start + 1, end, docstrings)

            # Define default fallback types based on file type
            if not symbol_type:
                if suffix in {".json", ".yaml", ".yml", ".xml", ".ini", ".env"}:
                    symbol_type = "ConfigBlock"
                elif suffix in {".css", ".scss", ".less"}:
                    symbol_type = "Stylesheet"
                elif suffix == ".md":
                    symbol_type = "Markdown"
                else:
                    symbol_type = "CodeBlock"

            # Create metadata
            chunk_id = f"{path}:{symbol_name or 'chunk'}:{start + 1}"
            metadata = {
                "chunk_id": chunk_id,
                "name": symbol_name or path.name,
                "type": symbol_type,
                "file": str(path),
                "start_line": start + 1,
                "end_line": end,
                "parent": None,
                "docstring": docstring,
                "imports": imports,
                "chunk_index": chunk_idx,
                "total_chunks": total_chunks_est,
                "code": chunk_code
            }

            chunks.append(metadata)
            chunk_idx += 1

            # Advance sliding window
            if end >= total_lines:
                break
            start += (self.max_chunk_lines - self.chunk_overlap)

        # Correct the actual total chunks in metadata
        for chunk in chunks:
            chunk["total_chunks"] = len(chunks)

        return chunks

    # =====================================================
    # IMPORT EXTRACTION
    # =====================================================

    def extract_imports(self, lines, suffix):
        imports = []
        # We only scan the first 100 lines for imports to save time
        scan_limit = min(100, len(lines))

        for i in range(scan_limit):
            line = lines[i]
            if suffix == ".java":
                match = self.java_import_pattern.match(line)
                if match:
                    imports.append(match.group(1))
            elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
                match = self.js_ts_import_pattern.match(line)
                if match:
                    imports.append(match.group(1))
                else:
                    match = self.require_import_pattern.search(line)
                    if match:
                        imports.append(match.group(1))
        return list(set(imports))

    # =====================================================
    # COMMENT / DOCSTRING EXTRACTION
    # =====================================================

    def extract_block_comments(self, source):
        # Extract JSDoc / JavaDoc blocks with their line numbers
        docstrings = []
        # Find all /** ... */ or /* ... */ blocks
        pattern = re.compile(r'/\*\*([\s\S]*?)\*/|/\*([\s\S]*?)\*/')
        
        for match in pattern.finditer(source):
            comment_text = match.group(1) or match.group(2)
            comment_text = comment_text.strip()
            
            # Find the starting line of this comment
            start_pos = match.start()
            start_line = source[:start_pos].count('\n') + 1
            end_line = start_line + comment_text.count('\n')
            
            docstrings.append({
                "start": start_line,
                "end": end_line,
                "text": comment_text
            })
        return docstrings

    def find_relevant_docstring(self, chunk_start, chunk_end, docstrings):
        # Return the docstring that overlaps with or directly precedes the chunk
        best_doc = ""
        for doc in docstrings:
            # If the docstring is within the chunk or just above it (up to 5 lines above)
            if (doc["start"] >= chunk_start and doc["start"] <= chunk_end) or \
               (doc["end"] >= chunk_start - 5 and doc["end"] <= chunk_start):
                best_doc = doc["text"]
                break
        return best_doc

    # =====================================================
    # SYMBOL DETECTION
    # =====================================================

    def detect_symbol(self, chunk_lines, suffix, default_name):
        # Detect the first prominent symbol declaration in the chunk lines
        for line in chunk_lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("//") or line_str.startswith("*") or line_str.startswith("/*"):
                continue

            if suffix == ".java":
                match = self.java_class_pattern.search(line)
                if match:
                    return match.group(1), "ClassDef"
                match = self.java_interface_pattern.search(line)
                if match:
                    return match.group(1), "InterfaceDef"
                match = self.java_method_pattern.search(line)
                if match:
                    return match.group(1), "FunctionDef"

            elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
                match = self.js_class_pattern.search(line)
                if match:
                    return match.group(1), "ClassDef"
                match = self.js_export_default_pattern.search(line)
                if match:
                    return match.group(1) or default_name, "FunctionDef"
                match = self.js_function_pattern.search(line)
                if match:
                    return match.group(1), "FunctionDef"
                match = self.js_arrow_fn_pattern.search(line)
                if match:
                    return match.group(1), "FunctionDef"
                match = self.js_export_const_pattern.search(line)
                if match:
                    return match.group(1), "FunctionDef"

        return None, None

