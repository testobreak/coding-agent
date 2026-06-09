# context/compression.py

from typing import List, Dict, Any


class ContextCompressor:

    def __init__(
        self,
        max_chunk_chars=4000,
        max_tool_output_chars=2000
    ):

        self.max_chunk_chars = max_chunk_chars

        self.max_tool_output_chars = (
            max_tool_output_chars
        )

    # =====================================================
    # CHUNK COMPRESSION
    # =====================================================

    def compress_chunks(
        self,
        chunks: List[Dict[str, Any]],
        primary_files: List[str] = None
    ):

        compressed = []

        seen = set()
        outlined_files = set()

        for chunk in chunks:

            chunk_id = chunk.get(
                "chunk_id"
            )

            if chunk_id in seen:
                continue

            seen.add(chunk_id)

            file_path = chunk.get("file", "")
            is_primary = primary_files is None or file_path in primary_files

            if is_primary:
                code = (
                    chunk.get("code")
                    or chunk.get("content")
                    or ""
                )
                content = self.truncate(
                    code,
                    self.max_chunk_chars
                )
                symbol_name = chunk.get("name", "") or chunk.get("symbol", "")
                chunk_type = chunk.get("type", "")
            else:
                if file_path in outlined_files:
                    # Skip duplicate outlines for the same secondary file
                    continue
                outlined_files.add(file_path)
                content = self.build_file_outline(file_path)
                symbol_name = "Secondary File Outline"
                chunk_type = "OUTLINE"

            compressed.append({

                "chunk_id":
                    chunk_id,

                "file":
                    file_path,

                "symbol":
                    symbol_name,

                "type":
                    chunk_type,

                "score":
                    round(
                        chunk.get("score", 0.0) or 0.0,
                        4
                    ),

                "content":
                    content
            })

        return compressed

    # =====================================================
    # TOOL OUTPUT COMPRESSION
    # =====================================================

    def compress_tool_outputs(
        self,
        outputs
    ):

        compressed = []

        for output in outputs:

            compressed.append({

                "tool":
                    output.get("tool"),

                "status":
                    output.get("status"),

                "result":
                    self.truncate(
                        str(
                            output.get(
                                "result",
                                ""
                            )
                        ),
                        self.max_tool_output_chars
                    )
            })

        return compressed

    # =====================================================
    # TRUNCATION
    # =====================================================

    def truncate(
        self,
        text,
        limit
    ):

        if not text:
            return ""

        if len(text) <= limit:
            return text

        return (
            text[:limit]
            + "\n\n...[TRUNCATED]..."
        )

    # =====================================================
    # FILE OUTLINE GENERATION
    # =====================================================

    def build_file_outline(self, file_path: str, session=None) -> str:
        """
        Builds a compact textual outline of the classes and methods declared in a file.
        """
        from repository_intelligence.db.connection import SessionLocal
        from repository_intelligence.models.symbol import Symbol
        from repository_intelligence.models.file import File

        db_session = session if session is not None else SessionLocal()
        close_session = True if session is None else False

        try:
            file_row = db_session.query(File).filter(File.path == file_path).first()
            if not file_row:
                return f"File: {file_path} (No database index found)"

            symbols = db_session.query(Symbol).filter(Symbol.file_id == file_row.id).order_by(Symbol.start_line).all()
            if not symbols:
                return f"File: {file_path} (No symbols indexed)"

            # Group symbols logically by parent/indentation
            outline_lines = [f"File: {file_path} (Outlined Symbols)"]
            for s in symbols:
                indent = "  "
                if s.parent_symbol_id:
                    indent = "    "
                
                sig = s.signature or s.name
                # Keep signature clean and compact
                sig = sig.replace("\n", " ").strip()
                outline_lines.append(f"{indent}- {s.symbol_type} {s.name} (Signature: {sig})")
            
            return "\n".join(outline_lines)
        except Exception as e:
            return f"File: {file_path} (Error building outline: {e})"
        finally:
            if close_session:
                db_session.close()
