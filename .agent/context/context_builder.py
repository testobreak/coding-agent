# context/context_builder.py
#
# Dedicated Context Engineering Subsystem.
# Combines intent analysis, target resolution, graph expansion bounded by radius,
# blast radius impact analysis, snippet extraction, and ranking into a ContextPackage.

import os
from typing import List, Dict, Any, Optional
from sqlalchemy import or_
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.symbol import Test as DBTest
from repository_intelligence.models.file import File

from context.context_package import (
    ContextPackage,
    GoalIntent,
    ResolvedSymbol,
    ContextRadius,
    Snippet,
    SymbolContextPackage
)
from editing.symbol_handle import SymbolHandle
from context.goal_analyzer import GoalAnalyzer
from context.snippet_builder import SnippetBuilder

# Compatibility alias
PlanningContext = ContextPackage

class ContextBuilder:
    def __init__(self, retrieval_pipeline, state_manager=None, radius: ContextRadius = ContextRadius.LOCAL):
        self.pipeline = retrieval_pipeline
        self.state_manager = state_manager
        self.radius = radius
        self.analyzer = GoalAnalyzer()
        self.snippet_builder = SnippetBuilder()
        from memory.experience_retriever import ExperienceRetriever
        self.experience_retriever = ExperienceRetriever()

    def build_planning_context(
        self,
        goal: str,
        state=None,
        radius: Optional[ContextRadius] = None,
        session=None
    ) -> ContextPackage:
        """
        Assembles all codebase context and system memory into a ContextPackage.
        """
        print(f"[ContextBuilder] Assembling context package for goal: {goal}")
        
        if radius is None:
            radius = getattr(self, "radius", ContextRadius.LOCAL)

        db_sess = session
        close_session = False
        if db_sess is None:
            db_sess = SessionLocal()
            close_session = True

        try:
            # 1. Target Resolution
            from context.target_resolver import TargetResolver
            resolver = TargetResolver(db_session=db_sess)
            resolved_targets = resolver.resolve(goal, session=db_sess)
            
            primary_symbol = resolved_targets[0] if resolved_targets else None
            if primary_symbol:
                print(f"[ContextBuilder] Target resolved: {primary_symbol.fqn} (in {primary_symbol.file_path})")
            else:
                print("[ContextBuilder] No primary symbol resolved.")
            
            callers = []
            callees = []
            related_tests = []
            dependencies = []
            affected_symbols = []
            imports = []

            # 2. Graph Expansion Bounded by Radius
            is_fallback = primary_symbol and primary_symbol.symbol_id and primary_symbol.symbol_id.startswith("sym_fallback")
            if primary_symbol and radius != ContextRadius.DIRECT and not is_fallback:
                # Direct callers
                caller_relations = db_sess.query(SymbolRelationship).filter(
                    SymbolRelationship.target_symbol_id == primary_symbol.symbol_id
                ).all()
                caller_ids = [rel.source_symbol_id for rel in caller_relations if rel.source_symbol_id]
                if caller_ids:
                    db_callers = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        Symbol.id.in_(caller_ids)
                    ).all()
                    for sym in db_callers:
                        callers.append(SymbolHandle(
                            symbol_id=str(sym.id),
                            fqn=sym.qualified_name,
                            kind=sym.symbol_type or "unknown",
                            file_path=sym.file.path if sym.file else "",
                            start_line=sym.start_line if sym.start_line is not None else 1,
                            end_line=sym.end_line if sym.end_line is not None else 1
                        ))

                # Direct callees
                callee_relations = db_sess.query(SymbolRelationship).filter(
                    SymbolRelationship.source_symbol_id == primary_symbol.symbol_id
                ).all()
                for rel in callee_relations:
                    if rel.target_symbol_id:
                        sym = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                            Symbol.id == rel.target_symbol_id
                        ).first()
                        if sym:
                            callees.append(SymbolHandle(
                                symbol_id=str(sym.id),
                                fqn=sym.qualified_name,
                                kind=sym.symbol_type or "unknown",
                                file_path=sym.file.path if sym.file else "",
                                start_line=sym.start_line if sym.start_line is not None else 1,
                                end_line=sym.end_line if sym.end_line is not None else 1
                            ))
                    elif rel.target_name:
                        syms = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                            or_(
                                Symbol.name == rel.target_name,
                                Symbol.qualified_name == rel.target_name
                            )
                        ).all()
                        for sym in syms:
                            callees.append(SymbolHandle(
                                symbol_id=str(sym.id),
                                fqn=sym.qualified_name,
                                kind=sym.symbol_type or "unknown",
                                file_path=sym.file.path if sym.file else "",
                                start_line=sym.start_line if sym.start_line is not None else 1,
                                end_line=sym.end_line if sym.end_line is not None else 1
                            ))

                # Direct tests
                symbol_ids_for_test = [primary_symbol.symbol_id] if not is_fallback else []
                seen_test_keys = set()
                if symbol_ids_for_test:
                    db_primary = db_sess.query(Symbol).filter(Symbol.id == primary_symbol.symbol_id).first()
                    if db_primary and db_primary.parent_symbol_id:
                        symbol_ids_for_test.append(str(db_primary.parent_symbol_id))
                    if "." in primary_symbol.fqn:
                        class_fqn = ".".join(primary_symbol.fqn.split(".")[:-1])
                        db_class = db_sess.query(Symbol).filter(Symbol.qualified_name == class_fqn).first()
                        if db_class:
                            symbol_ids_for_test.append(str(db_class.id))

                    db_tests = db_sess.query(DBTest, File.path).join(File, DBTest.file_id == File.id).filter(
                        DBTest.target_symbol_id.in_(symbol_ids_for_test)
                    ).all()
                    for t, file_path in db_tests:
                        key = (t.name, file_path)
                        seen_test_keys.add(key)
                        # Query corresponding test symbol
                        tsym = db_sess.query(Symbol).filter(
                            Symbol.name == t.name,
                            Symbol.file_id == t.file_id
                        ).first()
                        if tsym:
                            related_tests.append(SymbolHandle(
                                symbol_id=str(tsym.id),
                                fqn=tsym.qualified_name,
                                kind=tsym.symbol_type or "class",
                                file_path=file_path,
                                start_line=tsym.start_line,
                                end_line=tsym.end_line
                            ))
                        else:
                            related_tests.append(SymbolHandle(
                                symbol_id=str(t.id),
                                fqn=t.name,
                                kind="class",
                                file_path=file_path,
                                start_line=1,
                                end_line=100
                            ))

                # Heuristic tests
                primary_name = primary_symbol.fqn.split(".")[-1]
                heuristic_names = [f"{primary_name}Test", f"{primary_name}Tests", f"{primary_name}Spec"]
                db_heuristic_symbols = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                    Symbol.name.in_(heuristic_names)
                ).all()
                for hsym in db_heuristic_symbols:
                    key = (hsym.name, hsym.file.path if hsym.file else "")
                    if key not in seen_test_keys:
                        seen_test_keys.add(key)
                        related_tests.append(SymbolHandle(
                            symbol_id=str(hsym.id),
                            fqn=hsym.qualified_name,
                            kind=hsym.symbol_type or "class",
                            file_path=hsym.file.path if hsym.file else "",
                            start_line=hsym.start_line if hsym.start_line is not None else 1,
                            end_line=hsym.end_line if hsym.end_line is not None else 1
                        ))

                if radius == ContextRadius.EXTENDED and not is_fallback:
                    # Dependencies (e.g. USES/INHERITS relationships)
                    dep_relations = db_sess.query(SymbolRelationship).filter(
                        SymbolRelationship.source_symbol_id == primary_symbol.symbol_id,
                        SymbolRelationship.relationship_type.in_(["USES", "INHERITS", "IMPLEMENTS"])
                    ).all()
                    for rel in dep_relations:
                        if rel.target_symbol_id:
                            sym = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                                Symbol.id == rel.target_symbol_id
                            ).first()
                            if sym:
                                dependencies.append(SymbolHandle(
                                    symbol_id=str(sym.id),
                                    fqn=sym.qualified_name,
                                    kind=sym.symbol_type or "unknown",
                                    file_path=sym.file.path if sym.file else "",
                                    start_line=sym.start_line if sym.start_line is not None else 1,
                                    end_line=sym.end_line if sym.end_line is not None else 1
                                ))

                    # imports list
                    db_file = db_sess.query(File).filter(File.path == primary_symbol.file_path).first()
                    if db_file:
                        imports_relations = db_sess.query(SymbolRelationship).filter(
                            SymbolRelationship.source_file_id == db_file.id,
                            SymbolRelationship.relationship_type == "IMPORTS"
                        ).all()
                        imports = [rel.target_name for rel in imports_relations if rel.target_name]
                    else:
                        imports = []
                    if not imports and primary_symbol.file_path:
                        # Fallback: scan primary symbol file lines for imports
                        full_path = os.path.join(os.getcwd(), primary_symbol.file_path)
                        if os.path.exists(full_path):
                            try:
                                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                    for line in f:
                                        if line.strip().startswith("import "):
                                            imports.append(line.strip().replace("import ", "").replace(";", ""))
                            except Exception:
                                pass

            # 3. Impact Analysis & Risk Score
            risk_score = 0.10
            if primary_symbol:
                from context.impact_analyzer import ImpactAnalyzer
                analyzer = ImpactAnalyzer(db_session=db_sess)
                report = analyzer.analyze(primary_symbol, session=db_sess)
                risk_score = report.risk_score
                if radius == ContextRadius.EXTENDED:
                    affected_symbols = report.affected_symbols

            # 4. Snippet Assembly
            symbols_for_snippets = []
            if primary_symbol:
                symbols_for_snippets.append(primary_symbol)
            if radius != ContextRadius.DIRECT:
                symbols_for_snippets.extend(callers)
                symbols_for_snippets.extend(callees)
                symbols_for_snippets.extend(related_tests)
            if radius == ContextRadius.EXTENDED:
                symbols_for_snippets.extend(dependencies)

            # Deduplicate by FQN
            seen_fqns = set()
            unique_symbols_for_snippets = []
            for s in symbols_for_snippets:
                if s.fqn not in seen_fqns:
                    seen_fqns.add(s.fqn)
                    unique_symbols_for_snippets.append(s)

            # Build snippets via snippet_builder
            resolved_for_snippets = []
            for s in unique_symbols_for_snippets:
                name = s.fqn.split(".")[-1]
                resolved_for_snippets.append(ResolvedSymbol(
                    name=name,
                    file_path=s.file_path,
                    symbol_type=s.kind,
                    start_line=s.start_line,
                    end_line=s.end_line
                ))

            repo_root = os.getcwd()
            built_snippets = self.snippet_builder.build_snippets(resolved_for_snippets, repo_root)
            raw_snippets = []
            for bs in built_snippets:
                raw_snippets.append(Snippet(
                    symbol=bs["symbol"],
                    source=bs["code"],
                    relevance=0.0
                ))

            # 5. Rank Snippets using ContextRanker
            from context.context_ranker import ContextRanker
            ranker = ContextRanker()
            ranked_snippets = ranker.rank(
                snippets=raw_snippets,
                primary_symbol=primary_symbol,
                callers=callers,
                callees=callees,
                related_tests=related_tests,
                session=db_sess
            )

            # Limit top snippets based on radius
            max_snippets = 15 if radius == ContextRadius.LOCAL else (30 if radius == ContextRadius.EXTENDED else 5)
            ranked_snippets = ranked_snippets[:max_snippets]

            # 6. Intent Parse
            intent = self.analyzer.analyze(goal)

            # 7. Previous attempts
            previous_attempts = []
            if state:
                failed_steps = getattr(state, "failed_steps", []) or []
                for step in failed_steps:
                    previous_attempts.append(f"Failed Step: {step}")
                test_failures = getattr(state, "test_failures", []) or []
                for failure in test_failures:
                    msg = failure.get("message") or failure.get("error") or str(failure) if isinstance(failure, dict) else str(failure)
                    previous_attempts.append(f"Test Failure: {msg}")
                reflections = getattr(state, "reflections", []) or []
                for ref in reflections:
                    previous_attempts.append(f"Critic Reflection: {ref}")

            # 8. Retrieve Past Experiences from Execution Memory
            past_episodes = []
            past_plans = []
            past_repairs = []
            try:
                past_episodes = self.experience_retriever.find_similar_episodes(goal, limit=3)
                goal_type = intent.action if intent else "modify"
                past_plans = self.experience_retriever.get_successful_plans(goal_type, limit=3)
                past_repairs = self.experience_retriever.get_failure_repairs("MISSING_IMPORT", limit=3)
            except Exception as ex:
                print(f"[ContextBuilder] Experience retrieval warning: {ex}")

            return ContextPackage(
                goal=goal,
                primary_symbol=primary_symbol,
                callers=callers,
                callees=callees,
                related_tests=related_tests,
                imports=imports,
                dependencies=dependencies,
                affected_symbols=affected_symbols,
                snippets=ranked_snippets,
                risk_score=risk_score,
                confidence=0.90 if primary_symbol else 0.50,
                intent=intent,
                previous_attempts=previous_attempts,
                past_episodes=past_episodes,
                past_plans=past_plans,
                past_repairs=past_repairs
            )

        except Exception as e:
            print(f"[ContextBuilder] Error compilation: {e}")
            import traceback
            traceback.print_exc()
            # Minimal fallback package
            return ContextPackage(
                goal=goal,
                primary_symbol=None,
                intent=self.analyzer.analyze(goal),
                previous_attempts=[]
            )
        finally:
            if close_session and db_sess:
                db_sess.close()

    def build_symbol_context_package(self, target_symbol: SymbolHandle, session=None) -> SymbolContextPackage:
        """
        Traverses the codebase relationship graph to construct a SymbolContextPackage.
        """
        db_sess = session
        close_session = False
        if db_sess is None:
            db_sess = SessionLocal()
            close_session = True
        
        try:
            # Query callers
            callers = []
            caller_relations = db_sess.query(SymbolRelationship).filter(
                SymbolRelationship.target_symbol_id == target_symbol.symbol_id
            ).all()
            caller_ids = [rel.source_symbol_id for rel in caller_relations if rel.source_symbol_id]
            if caller_ids:
                db_callers = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                    Symbol.id.in_(caller_ids)
                ).all()
                for sym in db_callers:
                    callers.append(SymbolHandle(
                        symbol_id=str(sym.id),
                        fqn=sym.qualified_name,
                        kind=sym.symbol_type or "unknown",
                        file_path=sym.file.path if sym.file else "",
                        start_line=sym.start_line if sym.start_line is not None else 1,
                        end_line=sym.end_line if sym.end_line is not None else 1
                    ))

            # Query callees
            callees = []
            callee_relations = db_sess.query(SymbolRelationship).filter(
                SymbolRelationship.source_symbol_id == target_symbol.symbol_id
            ).all()
            for rel in callee_relations:
                if rel.target_symbol_id:
                    sym = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        Symbol.id == rel.target_symbol_id
                    ).first()
                    if sym:
                        callees.append(SymbolHandle(
                            symbol_id=str(sym.id),
                            fqn=sym.qualified_name,
                            kind=sym.symbol_type or "unknown",
                            file_path=sym.file.path if sym.file else "",
                            start_line=sym.start_line if sym.start_line is not None else 1,
                            end_line=sym.end_line if sym.end_line is not None else 1
                        ))

            # Query tests
            tests = []
            symbol_ids_for_test = [target_symbol.symbol_id]
            db_tests = db_sess.query(DBTest, File.path).join(File, DBTest.file_id == File.id).filter(
                DBTest.target_symbol_id.in_(symbol_ids_for_test)
            ).all()
            for t, file_path in db_tests:
                tsym = db_sess.query(Symbol).filter(
                    Symbol.name == t.name,
                    Symbol.file_id == t.file_id
                ).first()
                if tsym:
                    tests.append(SymbolHandle(
                        symbol_id=str(tsym.id),
                        fqn=tsym.qualified_name,
                        kind=tsym.symbol_type or "class",
                        file_path=file_path,
                        start_line=tsym.start_line,
                        end_line=tsym.end_line
                    ))

            # Query interfaces
            interfaces = []
            iface_relations = db_sess.query(SymbolRelationship).filter(
                SymbolRelationship.source_symbol_id == target_symbol.symbol_id,
                SymbolRelationship.relationship_type.in_(["IMPLEMENTS", "INHERITS", "EXTENDS"])
            ).all()
            for rel in iface_relations:
                if rel.target_symbol_id:
                    sym = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        Symbol.id == rel.target_symbol_id
                    ).first()
                    if sym:
                        interfaces.append(SymbolHandle(
                            symbol_id=str(sym.id),
                            fqn=sym.qualified_name,
                            kind=sym.symbol_type or "unknown",
                            file_path=sym.file.path if sym.file else "",
                            start_line=sym.start_line if sym.start_line is not None else 1,
                            end_line=sym.end_line if sym.end_line is not None else 1
                        ))

            # Query implementations
            implementations = []
            impl_relations = db_sess.query(SymbolRelationship).filter(
                SymbolRelationship.target_symbol_id == target_symbol.symbol_id,
                SymbolRelationship.relationship_type.in_(["IMPLEMENTS", "INHERITS", "EXTENDS"])
            ).all()
            for rel in impl_relations:
                if rel.source_symbol_id:
                    sym = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        Symbol.id == rel.source_symbol_id
                    ).first()
                    if sym:
                        implementations.append(SymbolHandle(
                            symbol_id=str(sym.id),
                            fqn=sym.qualified_name,
                            kind=sym.symbol_type or "unknown",
                            file_path=sym.file.path if sym.file else "",
                            start_line=sym.start_line if sym.start_line is not None else 1,
                            end_line=sym.end_line if sym.end_line is not None else 1
                        ))

            # Query related symbols (e.g. DTOs, USES/DEPENDS relations)
            related_symbols = []
            rel_relations = db_sess.query(SymbolRelationship).filter(
                SymbolRelationship.source_symbol_id == target_symbol.symbol_id,
                SymbolRelationship.relationship_type.in_(["USES", "DEPENDS"])
            ).all()
            for rel in rel_relations:
                if rel.target_symbol_id:
                    sym = db_sess.query(Symbol).join(File, Symbol.file_id == File.id).filter(
                        Symbol.id == rel.target_symbol_id
                    ).first()
                    if sym:
                        related_symbols.append(SymbolHandle(
                            symbol_id=str(sym.id),
                            fqn=sym.qualified_name,
                            kind=sym.symbol_type or "unknown",
                            file_path=sym.file.path if sym.file else "",
                            start_line=sym.start_line if sym.start_line is not None else 1,
                            end_line=sym.end_line if sym.end_line is not None else 1
                        ))

            return SymbolContextPackage(
                target_symbol=target_symbol,
                callers=callers,
                callees=callees,
                tests=tests,
                interfaces=interfaces,
                implementations=implementations,
                related_symbols=related_symbols
            )
        finally:
            if close_session and db_sess:
                db_sess.close()
