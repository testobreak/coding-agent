# editing/span_locator.py
import os
from dataclasses import dataclass
from typing import Optional, Tuple
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import SymbolSpan
from repository_intelligence.models.file import File

@dataclass
class EditRegion:
    file_path: str
    start_byte: int
    end_byte: int
    content: str
    start_line: int
    end_line: int

class SpanLocator:
    def find_edit_region(self, symbol_name: str, file_path: str) -> Optional[EditRegion]:
        db_session = SessionLocal()
        try:
            rel_path = file_path
            repo_root = os.getcwd()
            if os.path.basename(repo_root) == ".agent":
                repo_root = os.path.dirname(repo_root)
            try:
                rel_path = os.path.relpath(file_path, repo_root)
            except Exception:
                pass

            file_row = db_session.query(File).filter(File.path == rel_path).first()
            if not file_row:
                return None

            # Look up SymbolSpan in database
            span_record = None
            if "(" in symbol_name:
                span_record = db_session.query(SymbolSpan).filter(
                    SymbolSpan.file_id == file_row.id,
                    SymbolSpan.qualified_signature == symbol_name
                ).first()

            if not span_record:
                short_name = symbol_name.split(".")[-1].split("(")[0]
                span_record = db_session.query(SymbolSpan).filter(
                    SymbolSpan.file_id == file_row.id,
                    SymbolSpan.symbol == short_name
                ).first()

            if span_record:
                from repository.file_manager import FileManager
                file_mgr = FileManager(root=repo_root)
                content_full = file_mgr.read_file(file_path)

                start = span_record.start_byte
                end = span_record.end_byte
                
                content_bytes = content_full.encode("utf-8")
                content_len = len(content_bytes)
                start = max(0, min(start, content_len))
                end = max(start, min(end, content_len))

                sliced_content = content_bytes[start:end].decode("utf-8", errors="replace")

                lines_before = content_bytes[:start].decode("utf-8", errors="replace").splitlines()
                lines_inside = sliced_content.splitlines()
                start_line = len(lines_before) if lines_before else 1
                end_line = start_line + max(1, len(lines_inside)) - 1

                return EditRegion(
                    file_path=file_path,
                    start_byte=start,
                    end_byte=end,
                    content=sliced_content,
                    start_line=start_line,
                    end_line=end_line
                )
        except Exception as e:
            print(f"[SpanLocator] Error locating symbol span: {e}")
        finally:
            db_session.close()
        return None
