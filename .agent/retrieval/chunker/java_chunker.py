# retrieval/chunker/java_chunker.py
#
# Regex-based Java AST chunker.
# Produces one chunk per class-level declaration and one chunk per method,
# with accurate parent class name, JavaDoc docstring, and import list.
# No external Java parser required — pure Python.
#

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


# Matches class / abstract class / enum / @interface (annotation type)
_CLASS_RE = re.compile(
    r"""
    (?:(?:public|protected|private|abstract|final|static|strictfp)\s+)*
    (?:class|interface|enum|@interface)\s+
    (\w+)                     # captured name
    (?:\s*<[^>]*>)?           # optional generics
    (?:\s+extends\s+[\w<>, ]+)?
    (?:\s+implements\s+[\w<>, ]+)?
    \s*\{
    """,
    re.VERBOSE,
)

# Matches any method declaration with a body
_METHOD_RE = re.compile(
    r"""
    (?:(?:public|protected|private|static|final|synchronized|native|abstract|default|transient|volatile|\s)\s+)*
    (?:[\w<>\[\]?]+)\s+           # return type (may include generics)
    (\w+)\s*                      # method name — captured
    \(                            # open params
    """,
    re.VERBOSE,
)

# JavaDoc block: /** ... */
_JAVADOC_RE = re.compile(r"/\*\*[\s\S]*?\*/", re.MULTILINE)

# Single import line
_IMPORT_RE = re.compile(r"^\s*import\s+([\w.*]+)\s*;")

# Spring / Jakarta annotation on its own line
_ANNOTATION_RE = re.compile(r"^\s*@[\w(]")


class JavaChunker:
    """
    Splits a Java source file into semantically meaningful chunks:
    - One chunk for the class header (annotations + class declaration + fields)
    - One chunk per method (with its preceding JavaDoc if any)

    Each chunk carries: name, type, parent, file, start_line, end_line,
    imports, docstring, code, chunk_id.
    """

    def chunk_file(self, file_path) -> List[Dict[str, Any]]:
        path = Path(file_path)
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[JavaChunker Error] {file_path}: {e}")
            return []

        lines = source.splitlines()
        if not lines:
            return []

        imports = self._extract_imports(lines)
        javadocs = self._extract_javadocs(source)

        chunks: List[Dict[str, Any]] = []

        # Find class-level blocks
        class_blocks = self._find_class_blocks(lines)

        if not class_blocks:
            # Fallback: treat the entire file as one chunk
            return [self._make_chunk(
                name=path.stem,
                chunk_type="ClassDef",
                parent=None,
                file_path=str(path),
                start=1,
                end=len(lines),
                lines=lines,
                imports=imports,
                javadocs=javadocs,
                chunk_index=0,
            )]

        chunk_idx = 0
        for class_name, class_start, class_end in class_blocks:
            # Class header chunk (from class declaration to first method or end)
            first_method_line = self._find_first_method(lines, class_start, class_end)
            header_end = (first_method_line - 1) if first_method_line else class_end

            chunks.append(self._make_chunk(
                name=class_name,
                chunk_type="ClassDef",
                parent=None,
                file_path=str(path),
                start=class_start,
                end=header_end,
                lines=lines,
                imports=imports,
                javadocs=javadocs,
                chunk_index=chunk_idx,
            ))
            chunk_idx += 1

            # Method chunks
            method_blocks = self._find_method_blocks(lines, class_start, class_end, class_name)
            for method_name, m_start, m_end in method_blocks:
                chunks.append(self._make_chunk(
                    name=method_name,
                    chunk_type="MethodDef",
                    parent=class_name,
                    file_path=str(path),
                    start=m_start,
                    end=m_end,
                    lines=lines,
                    imports=imports,
                    javadocs=javadocs,
                    chunk_index=chunk_idx,
                ))
                chunk_idx += 1

        # Correct total chunks count
        total = len(chunks)
        for c in chunks:
            c["total_chunks"] = total

        return chunks

    # =========================================================
    # CHUNK BUILDER
    # =========================================================

    def _make_chunk(
        self,
        name: str,
        chunk_type: str,
        parent: Optional[str],
        file_path: str,
        start: int,
        end: int,
        lines: List[str],
        imports: List[str],
        javadocs: List[Dict],
        chunk_index: int,
    ) -> Dict[str, Any]:
        code_lines = lines[start - 1:end]
        code = "\n".join(code_lines)
        docstring = self._find_preceding_javadoc(start, javadocs)
        chunk_id = f"{file_path}:{name}:{start}"
        return {
            "chunk_id": chunk_id,
            "name": name,
            "type": chunk_type,
            "parent": parent,
            "file": file_path,
            "start_line": start,
            "end_line": end,
            "imports": imports,
            "docstring": docstring,
            "code": code,
            "chunk_index": chunk_index,
            "total_chunks": 0,  # filled in after all chunks built
        }

    # =========================================================
    # CLASS BLOCK DETECTION
    # =========================================================

    def _find_class_blocks(
        self, lines: List[str]
    ) -> List[Tuple[str, int, int]]:
        """
        Returns [(class_name, start_line_1indexed, end_line_1indexed), ...]
        for each top-level class/interface/enum in the file.
        Uses brace counting to find the matching closing brace.
        """
        blocks = []
        i = 0
        total = len(lines)

        while i < total:
            line = lines[i]
            m = _CLASS_RE.search(line)
            if m:
                class_name = m.group(1)
                start = i + 1  # 1-indexed
                depth = line.count("{") - line.count("}")
                j = i + 1
                while j < total and depth > 0:
                    depth += lines[j].count("{") - lines[j].count("}")
                    j += 1
                end = j  # 1-indexed (inclusive)
                blocks.append((class_name, start, end))
                i = j
                continue
            i += 1

        return blocks

    # =========================================================
    # METHOD BLOCK DETECTION
    # =========================================================

    def _find_first_method(
        self, lines: List[str], class_start: int, class_end: int
    ) -> Optional[int]:
        for i in range(class_start, min(class_end, len(lines))):
            line = lines[i]
            if _METHOD_RE.search(line) and "{" in line:
                # Exclude field initialisers and constructors that look like fields
                if not self._is_field_line(line):
                    return i + 1  # 1-indexed
        return None

    def _find_method_blocks(
        self,
        lines: List[str],
        class_start: int,
        class_end: int,
        class_name: str,
    ) -> List[Tuple[str, int, int]]:
        """
        Returns [(method_name, start_1idx, end_1idx), ...] within the class body.
        """
        methods = []
        i = class_start  # 0-indexed scan (class_start is 1-indexed → first line inside class)
        limit = min(class_end, len(lines))

        while i < limit:
            line = lines[i]
            m = _METHOD_RE.search(line)
            if m and "{" in line and not self._is_field_line(line):
                method_name = m.group(1)
                # Skip constructor with same name as class (optional: keep as ConstructorDef)
                start = i + 1  # 1-indexed
                depth = line.count("{") - line.count("}")
                j = i + 1
                while j < limit and depth > 0:
                    depth += lines[j].count("{") - lines[j].count("}")
                    j += 1
                end = j  # 1-indexed inclusive
                # Include preceding annotations (up to 5 lines back)
                ann_start = self._find_annotation_start(lines, i)
                methods.append((method_name, ann_start, end))
                i = j
                continue
            i += 1

        return methods

    def _find_annotation_start(self, lines: List[str], method_line_0idx: int) -> int:
        """Walk backwards to include @Annotation lines above the method."""
        i = method_line_0idx - 1
        while i >= 0 and _ANNOTATION_RE.match(lines[i]):
            i -= 1
        return i + 2  # 1-indexed

    def _is_field_line(self, line: str) -> bool:
        """Heuristic: if line has = sign before { it's probably a field initialiser."""
        eq_pos = line.find("=")
        brace_pos = line.find("{")
        if eq_pos > 0 and (brace_pos < 0 or eq_pos < brace_pos):
            return True
        return False

    # =========================================================
    # IMPORT EXTRACTION
    # =========================================================

    def _extract_imports(self, lines: List[str]) -> List[str]:
        imports = []
        for line in lines[:100]:
            m = _IMPORT_RE.match(line)
            if m:
                imports.append(m.group(1))
        return imports

    # =========================================================
    # JAVADOC EXTRACTION
    # =========================================================

    def _extract_javadocs(self, source: str) -> List[Dict]:
        docs = []
        for match in _JAVADOC_RE.finditer(source):
            start_line = source[: match.start()].count("\n") + 1
            end_line = source[: match.end()].count("\n") + 1
            docs.append({
                "start": start_line,
                "end": end_line,
                "text": match.group(0).strip(),
            })
        return docs

    def _find_preceding_javadoc(
        self, symbol_line_1idx: int, javadocs: List[Dict]
    ) -> str:
        """Return the JavaDoc that ends within 3 lines before symbol_line."""
        for doc in reversed(javadocs):
            if 0 < (symbol_line_1idx - doc["end"]) <= 3:
                return doc["text"]
        return ""
