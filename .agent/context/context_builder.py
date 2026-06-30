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
        session=None,
        mode: Optional[str] = None,
        **kwargs
    ) -> ContextPackage:
        """
        Assembles all codebase context and system memory into a ContextPackage.
        """
        # Resolve task_id and active_file for caching
        task_id = None
        if state:
            task_id = getattr(state, "task_id", None)
        if not task_id:
            task_id = getattr(self.state_manager, "task_id", None) if getattr(self, "state_manager", None) else None
            
        active_file = None
        if state and getattr(state, "runtime_context", None):
            active_file = getattr(state.runtime_context, "active_file", None)
        if not active_file:
            from context.session_cache import SessionCache
            active_file = SessionCache.get_session("default").active_file

        if task_id:
            from context.cache import ContextCache
            cached = ContextCache.get(task_id, active_file)
            if cached and cached.symbol_context:
                print(f"[ContextBuilder] Cache hit! Reusing symbol context for task {task_id}, active_file {active_file}")
                return cached.symbol_context

        print(f"[ContextBuilder] Assembling context package for goal: {goal}")
        
        # Resolve policy
        from context.policy_engine import ContextPolicyEngine, ContextPolicy
        policy = kwargs.get("policy")
        if not policy:
            policy = ContextPolicyEngine.choose_context(goal, mode=mode)

        # Check for fast path bypass
        is_fast_path = False
        has_selection = False
        if state and getattr(state, "runtime_context", None):
            runtime_ctx = state.runtime_context
            selection = getattr(runtime_ctx, "selection", None)
            if selection:
                has_selection = True
        
        is_simple = False
        if has_selection:
            g_lower = goal.lower()
            local_refs = ["here", "this", "selection", "current"]
            complex_keywords = ["database system", "across multiple files", "architecture", "design", "refactor whole"]
            if any(ref in g_lower for ref in local_refs) and not any(kw in g_lower for kw in complex_keywords):
                is_simple = True
                
        if (has_selection and is_simple) or mode == "patch":
            print("Fast path activated: selection present and task is simple or patch mode active")
            is_fast_path = True

        if radius is None:
            radius = getattr(self, "radius", ContextRadius.LOCAL)

        db_sess = session
        close_session = False
        if db_sess is None:
            db_sess = SessionLocal()
            close_session = True

        try:
            if is_fast_path:
                print("[ContextBuilder] Executing super-fast context path.")
                ui_snippets = []
                nearby_snippets = []
                
                repo_root = os.getcwd()
                if os.path.basename(repo_root) == ".agent":
                    repo_root = os.path.dirname(repo_root)

                # 1. Active Selection snippet
                if state and getattr(state, "runtime_context", None):
                    runtime_ctx = state.runtime_context
                    selection = getattr(runtime_ctx, "selection", None)
                    if selection:
                        ui_snippets.append(Snippet(
                            symbol="active_selection",
                            source=selection,
                            relevance=1.0
                        ))
                        
                # 1.5 Active Diagnostics snippet
                if state and getattr(state, "runtime_context", None):
                    runtime_ctx = state.runtime_context
                    diagnostics = getattr(runtime_ctx, "diagnostics", None)
                    if diagnostics:
                        diag_texts = []
                        for d in diagnostics:
                            msg = getattr(d, "message", None) or (d.get("message") if isinstance(d, dict) else str(d))
                            file = getattr(d, "file", None) or (d.get("file") if isinstance(d, dict) else "")
                            line = getattr(d, "line", None) or (d.get("line") if isinstance(d, dict) else "")
                            diag_texts.append(f"{file}:{line} - {msg}")
                        if diag_texts:
                            ui_snippets.append(Snippet(
                                symbol="active_diagnostic",
                                source="\n".join(diag_texts),
                                relevance=1.0
                            ))
                        
                # 2. Active File Focus snippet
                focus_source = None
                if state and getattr(state, "runtime_context", None):
                    runtime_ctx = state.runtime_context
                    unsaved_buffer = getattr(runtime_ctx, "unsaved_buffer", None)
                    if unsaved_buffer:
                        focus_source = unsaved_buffer
                    elif active_file:
                        try:
                            full_path = os.path.join(repo_root, active_file)
                            from ide.virtual_workspace import VirtualWorkspace
                            workspace = VirtualWorkspace.get_instance()
                            if workspace.exists(full_path):
                                focus_source = workspace.read_file(full_path)
                        except Exception:
                            pass
                            
                if focus_source:
                    symbol_name = f"active_file_focus:{active_file}" if active_file else "active_file_focus"
                    ui_snippets.append(Snippet(
                        symbol=symbol_name,
                        source=focus_source,
                        relevance=1.0
                    ))

                # 3. Nearby Symbols in active file
                if active_file:
                    db_file = db_sess.query(File).filter(File.path == active_file).first()
                    if db_file:
                        nearby_syms = db_sess.query(Symbol).filter(Symbol.file_id == db_file.id).all()
                        resolved_for_snippets = []
                        for sym in nearby_syms:
                            resolved_for_snippets.append(ResolvedSymbol(
                                name=sym.name,
                                file_path=active_file,
                                symbol_type=sym.symbol_type or "unknown",
                                start_line=sym.start_line,
                                end_line=sym.end_line
                            ))
                        if resolved_for_snippets:
                            built = self.snippet_builder.build_snippets(resolved_for_snippets, repo_root)
                            for bs in built:
                                nearby_snippets.append(Snippet(
                                    symbol=bs["symbol"],
                                    source=bs["code"],
                                    relevance=0.8
                                ))
                
                # Combine snippets
                ranked_snippets = ui_snippets + nearby_snippets
                
                result_context = ContextPackage(
                    goal=goal,
                    primary_symbol=None,
                    callers=[],
                    callees=[],
                    related_tests=[],
                    imports=[],
                    dependencies=[],
                    affected_symbols=[],
                    snippets=ranked_snippets[:10],
                    risk_score=0.0,
                    confidence=1.0,
                    intent=None,
                    previous_attempts=[],
                    past_episodes=[],
                    past_plans=[],
                    past_repairs=[]
                )
                if task_id:
                    from context.cache import ContextCache
                    ContextCache.set(
                        task_id=task_id,
                        active_file=active_file,
                        repo_root=None,
                        assembled_prompt=None,
                        tokenized_prompt=None,
                        symbol_context=result_context
                    )
                return result_context

            primary_symbol = None
            callers = []
            callees = []
            related_tests = []
            dependencies = []
            affected_symbols = []
            imports = []
            risk_score = 0.10

            if not is_fast_path:
                # 0. Cursor-aware symbol localization (P0 Priority)
                cursor_symbol = None
                if state and getattr(state, "runtime_context", None):
                    runtime_ctx = state.runtime_context
                    active_file_rel = getattr(runtime_ctx, "active_file", None)
                    cursor_pos = getattr(runtime_ctx, "cursor_position", None)
                    if active_file_rel and cursor_pos:
                        line_num = cursor_pos[0] if isinstance(cursor_pos, (list, tuple)) else cursor_pos
                        if isinstance(line_num, int) and line_num > 0:
                            try:
                                from editing.ast_locator import ASTLocator
                                locator = ASTLocator()
                                repo_root = os.getcwd()
                                if os.path.basename(repo_root) == ".agent":
                                    repo_root = os.path.dirname(repo_root)
                                full_path = os.path.abspath(os.path.join(repo_root, active_file_rel))
                                
                                source_content = None
                                if hasattr(runtime_ctx, "unsaved_buffer") and runtime_ctx.unsaved_buffer:
                                    source_content = runtime_ctx.unsaved_buffer
                                else:
                                    if os.path.exists(full_path):
                                        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                            source_content = f.read()

                                node_info = locator.find_enclosing_node(full_path, line_num, source=source_content)
                                if node_info:
                                    cursor_symbol = SymbolHandle(
                                        symbol_id=f"sym_cursor_{node_info.name}",
                                        fqn=node_info.name,
                                        kind=node_info.node_type or "method",
                                        file_path=active_file_rel,
                                        start_line=node_info.start_line,
                                        end_line=node_info.end_line
                                    )
                                    print(f"[ContextBuilder] Cursor-aware symbol localized: {cursor_symbol.fqn} (Lines {cursor_symbol.start_line}-{cursor_symbol.end_line})")
                            except Exception as e:
                                print(f"[ContextBuilder] Warning: Cursor-aware localization failed: {e}")

                if cursor_symbol:
                    primary_symbol = cursor_symbol
                else:
                    # 1. Target Resolution
                    from context.target_resolver import TargetResolver
                    resolver = TargetResolver(db_session=db_sess)
                    resolved_targets = resolver.resolve(goal, session=db_sess)
                    primary_symbol = resolved_targets[0] if resolved_targets else None
                
                # Gating Layer 1: include_local_symbol
                if primary_symbol and not cursor_symbol and not policy.include_local_symbol:
                    primary_symbol = None

                if primary_symbol:
                    print(f"[ContextBuilder] Target resolved: {primary_symbol.fqn} (in {primary_symbol.file_path})")
                else:
                    print("[ContextBuilder] No primary symbol resolved.")
                
                # Gating Layer 2: include_repo_context
                is_fallback = primary_symbol and primary_symbol.symbol_id and primary_symbol.symbol_id.startswith("sym_fallback")
                if primary_symbol and radius != ContextRadius.DIRECT and not is_fallback and policy.include_repo_context:
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
                            from ide.virtual_workspace import VirtualWorkspace
                            workspace = VirtualWorkspace.get_instance()
                            if workspace.exists(full_path):
                                try:
                                    content = workspace.read_file(full_path)
                                    for line in content.splitlines():
                                        if line.strip().startswith("import "):
                                            imports.append(line.strip().replace("import ", "").replace(";", ""))
                                except Exception:
                                    pass

                # 3. Impact Analysis & Risk Score
                if primary_symbol and policy.include_repo_context:
                    from context.impact_analyzer import ImpactAnalyzer
                    analyzer = ImpactAnalyzer(db_session=db_sess)
                    report = analyzer.analyze(primary_symbol, session=db_sess)
                    risk_score = report.risk_score
                    if radius == ContextRadius.EXTENDED:
                        affected_symbols = report.affected_symbols

            # 4. Snippet Assembly
            symbols_for_snippets = []
            if primary_symbol and policy.include_local_symbol:
                symbols_for_snippets.append(primary_symbol)
            if radius != ContextRadius.DIRECT and policy.include_repo_context:
                symbols_for_snippets.extend(callers)
                symbols_for_snippets.extend(callees)
                symbols_for_snippets.extend(related_tests)
            if radius == ContextRadius.EXTENDED and policy.include_repo_context:
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
            if os.path.basename(repo_root) == ".agent":
                repo_root = os.path.dirname(repo_root)
            built_snippets = self.snippet_builder.build_snippets(resolved_for_snippets, repo_root)
            raw_snippets = []
            for bs in built_snippets:
                raw_snippets.append(Snippet(
                    symbol=bs["symbol"],
                    source=bs["code"],
                    relevance=0.0
                ))

            # Add UI Context Snippets (Layer 0) - Tier 1
            ui_snippets = []
            if policy.include_ui_context and state and getattr(state, "runtime_context", None):
                runtime_ctx = state.runtime_context
                
                # active_selection
                selection = getattr(runtime_ctx, "selection", None)
                if selection:
                    ui_snippets.append(Snippet(
                        symbol="active_selection",
                        source=selection,
                        relevance=1.0
                    ))
                
                # active_diagnostic
                diags = getattr(runtime_ctx, "diagnostics", None)
                if diags:
                    diag_texts = []
                    for d in diags:
                        msg = getattr(d, "message", None) or (d.get("message") if isinstance(d, dict) else str(d))
                        file = getattr(d, "file", None) or (d.get("file") if isinstance(d, dict) else "")
                        line = getattr(d, "line", None) or (d.get("line") if isinstance(d, dict) else "")
                        diag_texts.append(f"{file}:{line} - {msg}")
                    if diag_texts:
                        ui_snippets.append(Snippet(
                            symbol="active_diagnostic",
                            source="\n".join(diag_texts),
                            relevance=1.0
                        ))
                
                # active_file_focus
                active_file = getattr(runtime_ctx, "active_file", None)
                unsaved_buffer = getattr(runtime_ctx, "unsaved_buffer", None)
                
                focus_source = None
                if unsaved_buffer:
                    focus_source = unsaved_buffer
                elif active_file:
                    try:
                        full_path = os.path.join(repo_root, active_file)
                        from ide.virtual_workspace import VirtualWorkspace
                        workspace = VirtualWorkspace.get_instance()
                        if workspace.exists(full_path):
                            focus_source = workspace.read_file(full_path)
                    except Exception:
                        pass
                
                if focus_source:
                    symbol_name = f"active_file_focus:{active_file}" if active_file else "active_file_focus"
                    ui_snippets.append(Snippet(
                        symbol=symbol_name,
                        source=focus_source,
                        relevance=1.0
                    ))

            # Fetch budgets and firewall settings
            from context.policy_engine import ContextPolicyEngine
            budget = ContextPolicyEngine.get_budget(mode)
            firewalled = ContextPolicyEngine.is_firewalled(mode)

            # Diagnostics for scoring
            diagnostics = []
            if state and getattr(state, "runtime_context", None) and getattr(state.runtime_context, "diagnostics", None):
                diagnostics = state.runtime_context.diagnostics

            # Apply Tier 1 token budgeting using RelevanceRanker
            from context.relevance_ranker import RelevanceRanker
            primary_fqn = primary_symbol.fqn if primary_symbol else None

            # Rank and budget UI/Tier 1 snippets
            ui_snippets = RelevanceRanker.rank_and_budget(
                ui_snippets,
                goal, primary_fqn, diagnostics,
                token_limit=budget.get("tier1", 1800)
            )

            # Build and rank codebase / Tier 2 snippets
            other_snippets = [s for s in raw_snippets if s.symbol not in ("active_selection", "active_diagnostic") and not s.symbol.startswith("active_file_focus")]
            from context.context_ranker import ContextRanker
            ranker = ContextRanker()
            ranked_other_snippets = ranker.rank(
                snippets=other_snippets,
                primary_symbol=primary_symbol,
                callers=callers,
                callees=callees,
                related_tests=related_tests,
                session=db_sess
            )

            # Apply Tier 2 token budgeting on structural snippets
            ranked_other_snippets = RelevanceRanker.rank_and_budget(
                ranked_other_snippets,
                goal, primary_fqn, diagnostics,
                token_limit=budget.get("tier2", 2500)
            )

            # Combine Tier 1 and Tier 2 snippets
            ranked_snippets = ui_snippets + ranked_other_snippets

            # 6. Intent Parse
            intent = self.analyzer.analyze(goal)

            # 7. Previous attempts / reflections / memory (Tier 3)
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
            if policy.include_memory:
                try:
                    past_episodes = self.experience_retriever.find_similar_episodes(goal, limit=3)
                    goal_type = intent.action if intent else "modify"
                    past_plans = self.experience_retriever.get_successful_plans(goal_type, limit=3)
                    past_repairs = self.experience_retriever.get_failure_repairs("MISSING_IMPORT", limit=3)
                except Exception as ex:
                    print(f"[ContextBuilder] Experience retrieval warning: {ex}")

            # Enforce Context Firewall on Tier 3 elements
            if firewalled:
                previous_attempts = []
                past_episodes = []
                past_plans = []
                past_repairs = []
                callers = []
                callees = []
                related_tests = []
                dependencies = []
            else:
                tier3_limit = budget.get("tier3", 1500)
                limit_each = tier3_limit // 4
                previous_attempts = RelevanceRanker.rank_and_budget(
                    previous_attempts,
                    goal, primary_fqn, diagnostics,
                    token_limit=limit_each
                )
                past_episodes = RelevanceRanker.rank_and_budget(
                    past_episodes,
                    goal, primary_fqn, diagnostics,
                    token_limit=limit_each
                )
                past_plans = RelevanceRanker.rank_and_budget(
                    past_plans,
                    goal, primary_fqn, diagnostics,
                    token_limit=limit_each
                )
                past_repairs = RelevanceRanker.rank_and_budget(
                    past_repairs,
                    goal, primary_fqn, diagnostics,
                    token_limit=limit_each
                )

            result_context = ContextPackage(
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
            if task_id:
                ContextCache.set(
                    task_id=task_id,
                    active_file=active_file,
                    repo_root=None,
                    assembled_prompt=None,
                    tokenized_prompt=None,
                    symbol_context=result_context
                )
            return result_context

        except Exception as e:
            print(f"[ContextBuilder] Error compilation: {e}")
            import traceback
            traceback.print_exc()
            # Minimal fallback package
            result_context = ContextPackage(
                goal=goal,
                primary_symbol=None,
                intent=self.analyzer.analyze(goal),
                previous_attempts=[]
            )
            if task_id:
                ContextCache.set(
                    task_id=task_id,
                    active_file=active_file,
                    repo_root=None,
                    assembled_prompt=None,
                    tokenized_prompt=None,
                    symbol_context=result_context
                )
            return result_context
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
