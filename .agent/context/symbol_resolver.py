# context/symbol_resolver.py
#
# Symbol resolution logic. Maps target string identifiers to database Symbol and File entities.

from typing import List, Optional
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Symbol
from repository_intelligence.models.file import File
from context.context_package import ResolvedSymbol
from sqlalchemy import or_

class SymbolResolver:
    def resolve(self, symbol_name: str, session=None) -> List[ResolvedSymbol]:
        if not symbol_name or symbol_name == "unknown":
            return []
        
        close_session = False
        if session is None:
            session = SessionLocal()
            close_session = True
        
        resolved = []
        try:
            db_symbols = session.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                or_(
                    Symbol.name == symbol_name,
                    Symbol.qualified_name == symbol_name
                )
            ).all()

            for sym in db_symbols:
                resolved.append(ResolvedSymbol(
                    name=sym.name,
                    file_path=sym.file.path if sym.file else "",
                    symbol_type=sym.symbol_type or "unknown",
                    signature=sym.signature,
                    start_line=sym.start_line,
                    end_line=sym.end_line
                ))
        except Exception as e:
            print(f"[SymbolResolver] Warning: Failed resolving symbol {symbol_name}: {e}")
        finally:
            if close_session:
                session.close()
            
        return resolved
