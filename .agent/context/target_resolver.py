# context/target_resolver.py
#
# TargetResolver maps goal queries into target SymbolHandle objects.

import re
from typing import List, Optional
from sqlalchemy import or_
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Symbol
from repository_intelligence.models.file import File
from editing.symbol_handle import SymbolHandle
from context.goal_analyzer import GoalAnalyzer

class TargetResolver:
    def __init__(self, db_session=None):
        self.db_session = db_session
        self.analyzer = GoalAnalyzer()

    def resolve(self, goal: str, session=None) -> List[SymbolHandle]:
        """
        Resolves a goal string to a list of target SymbolHandle objects.
        """
        db_sess = session or self.db_session
        close_session = False
        if db_sess is None:
            db_sess = SessionLocal()
            close_session = True

        handles = []
        try:
            # 1. Parse using GoalAnalyzer
            intent = self.analyzer.analyze(goal)
            candidates = []
            if intent.target and intent.target != "unknown":
                candidates.append(intent.target)

            # 2. Extract any other CamelCase or dotted symbols from the goal
            camel_case = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', goal)
            dotted = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_\.]*\.[A-Z][a-zA-Z0-9_]*\b', goal)
            # Dotted words that might end with a method call (e.g. EmployeeService.saveEmployee)
            dotted_methods = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_\.]*\.[a-zA-Z0-9_]+\b', goal)

            for c in camel_case + dotted + dotted_methods:
                if c not in candidates:
                    candidates.append(c)

            # Filter out common query/stop words
            stop_words = {"add", "fix", "create", "implement", "refactor", "remove", "delete", "update", "modify", "logging", "to", "flow", "save"}
            candidates = [c for c in candidates if c.lower() not in stop_words]

            # Sort candidates: dotted names first, then by length descending (more specific first)
            candidates.sort(key=lambda x: ('.' in x, len(x)), reverse=True)

            # 3. Lookup candidates in database
            seen_ids = set()
            for cand in candidates:
                # Direct match (name or qualified_name)
                db_symbols = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                    or_(
                        Symbol.name == cand,
                        Symbol.qualified_name == cand,
                        Symbol.qualified_name.endswith("." + cand)
                    )
                ).all()

                # Dotted target split lookup (e.g., EmployeeService.saveEmployee)
                if not db_symbols and "." in cand:
                    parts = cand.split(".")
                    method_part = parts[-1]
                    class_part = parts[-2]
                    db_symbols = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        Symbol.name == method_part,
                        Symbol.qualified_name.contains(class_part)
                    ).all()

                # Fuzzy lookup as fallback for this candidate
                if not db_symbols:
                    db_symbols = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        or_(
                            Symbol.name.like(f"%{cand}%"),
                            Symbol.qualified_name.like(f"%{cand}%")
                        )
                    ).limit(5).all()

                for sym in db_symbols:
                    if sym.id not in seen_ids:
                        seen_ids.add(sym.id)
                        handles.append(SymbolHandle(
                            symbol_id=str(sym.id),
                            fqn=sym.qualified_name,
                            kind=sym.symbol_type or "unknown",
                            file_path=sym.file.path if sym.file else "",
                            start_line=sym.start_line if sym.start_line is not None else 1,
                            end_line=sym.end_line if sym.end_line is not None else 1
                        ))

            # 4. Final fallback if absolutely nothing was found, but we have candidate strings
            if not handles and candidates:
                # Let's check if there is any file name matching
                for cand in candidates:
                    db_files = db_sess.query(File).filter(File.path.contains(cand)).all()
                    for f in db_files:
                        handles.append(SymbolHandle(
                            symbol_id=f"sym_fallback_{cand}",
                            fqn=cand,
                            kind="class",
                            file_path=f.path,
                            start_line=1,
                            end_line=100
                        ))
                        break
                    if handles:
                        break

            # If still nothing resolved, construct a generic fallback handle
            if not handles:
                fallback_name = candidates[0] if candidates else "UnknownSymbol"
                handles.append(SymbolHandle(
                    symbol_id=f"sym_fallback_{fallback_name}",
                    fqn=fallback_name,
                    kind="fallback",
                    file_path="",
                    start_line=1,
                    end_line=1
                ))

        except Exception as e:
            print(f"[TargetResolver] Warning: Failed target resolution: {e}")
        finally:
            if close_session:
                db_sess.close()

        return handles
