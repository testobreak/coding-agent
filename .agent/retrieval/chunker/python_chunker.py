# retrieval/chunker/python_chunker.py

import ast

from pathlib import Path


class PythonChunker:

    def __init__(self):

        self.max_chunk_lines = 120

        self.chunk_overlap = 20

    # =====================================================
    # MAIN
    # =====================================================

    def chunk_file(
        self,
        file_path
    ):

        path = Path(file_path)

        try:

            source = path.read_text(
                encoding="utf-8",
                errors="ignore"
            )

        except Exception as e:

            print(
                f"[Chunker Error] "
                f"{file_path}: {e}"
            )

            return []

        try:

            tree = ast.parse(source)

        except SyntaxError:

            return []

        imports = self.extract_imports(
            tree
        )

        lines = source.splitlines()

        chunks = []

        for node in tree.body:

            if isinstance(node, (
                ast.ClassDef,
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )):

                built = self.process_node(

                    node=node,

                    lines=lines,

                    imports=imports,

                    path=path,

                    parent=None
                )

                chunks.extend(built)

        return chunks

    # =====================================================
    # NODE PROCESSING
    # =====================================================

    def process_node(
        self,
        node,
        lines,
        imports,
        path,
        parent
    ):

        chunks = []

        start = node.lineno

        end = node.end_lineno

        node_lines = lines[start - 1:end]

        metadata = {

            "chunk_id":
                f"{path}:{node.name}:{start}",

            "name":
                node.name,

            "type":
                type(node).__name__,

            "file":
                str(path),

            "start_line":
                start,

            "end_line":
                end,

            "parent":
                parent,

            "docstring":
                ast.get_docstring(node) or "",

            "imports":
                imports
        }

        # =============================================
        # SMALL CHUNK
        # =============================================

        if len(node_lines) <= self.max_chunk_lines:

            chunks.append({

                **metadata,

                "chunk_index": 0,

                "total_chunks": 1,

                "code":
                    "\n".join(node_lines)
            })

        # =============================================
        # LARGE CHUNK
        # =============================================

        else:

            split_chunks = self.split_chunk(
                node_lines
            )

            for i, split in enumerate(
                split_chunks
            ):

                chunks.append({

                    **metadata,

                    "chunk_index": i,

                    "total_chunks":
                        len(split_chunks),

                    "code":
                        split
                })

        # =============================================
        # CLASS CHILDREN
        # =============================================

        if isinstance(node, ast.ClassDef):

            for child in node.body:

                if isinstance(child, (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef
                )):

                    child_chunks = (
                        self.process_node(

                            node=child,

                            lines=lines,

                            imports=imports,

                            path=path,

                            parent=node.name
                        )
                    )

                    chunks.extend(
                        child_chunks
                    )

        return chunks

    # =====================================================
    # SPLIT LARGE CHUNKS
    # =====================================================

    def split_chunk(
        self,
        lines
    ):

        chunks = []

        start = 0

        while start < len(lines):

            end = start + self.max_chunk_lines

            piece = lines[start:end]

            chunks.append(
                "\n".join(piece)
            )

            start += (
                self.max_chunk_lines
                - self.chunk_overlap
            )

        return chunks

    # =====================================================
    # IMPORT EXTRACTION
    # =====================================================

    def extract_imports(
        self,
        tree
    ):

        imports = []

        for node in ast.walk(tree):

            if isinstance(node, ast.Import):

                for alias in node.names:

                    imports.append(
                        alias.name
                    )

            elif isinstance(
                node,
                ast.ImportFrom
            ):

                imports.append(
                    node.module or ""
                )

        return imports
