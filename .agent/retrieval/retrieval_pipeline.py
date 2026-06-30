# retrieval/retrieval_pipeline.py

from collections import defaultdict
from typing import List, Dict, Any, Union, Optional
from retrieval.hybrid_ranker import HybridRanker
from retrieval.feature_extractor import RetrievalContext

class RetrievalPipeline:

    def __init__(
        self,
        retriever
    ):
        self.retriever = retriever
        self.ranking_engine = HybridRanker()

    def retrieve(
        self,
        query: str,
        context: Optional[RetrievalContext] = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        # Fast-path 1: Lexical/symbol bypass for pure symbol name lookups
        import re
        is_lexical_only = False
        query_clean = query.strip()
        if re.match(r"^[a-zA-Z0-9_\.]+$", query_clean):
            is_lexical_only = True

        candidates = []
        if is_lexical_only:
            query_lower = query_clean.lower()
            for chunk in self.retriever.chunks:
                f = (chunk.get("file") or "").lower()
                if any(p in f for p in [".agent/", "repository_intelligence/", "venv/", "node_modules/", ".git/"]):
                    continue
                name = (chunk.get("name") or "").lower()
                symbol = (chunk.get("symbol") or "").lower()
                if query_lower == name or query_lower == symbol or query_lower in f:
                    candidates.append({"score": 100.0, "chunk": chunk})
            
            from retrieval.ranker import SpecRanker
            reranked = SpecRanker.rerank_candidates(candidates, context=context)
            return [{"chunk": item["chunk"], "score": item["score"]} for item in reranked[:top_k]]

        # Fast-path 2: Graph shortcut for test queries ("tests for <Symbol>")
        if "tests for" in query.lower():
            target_symbol = query.lower().replace("tests for", "").strip()
            if re.match(r"^[a-zA-Z0-9_\.]+$", target_symbol):
                from repository_intelligence.db.connection import SessionLocal
                from repository_intelligence.models.symbol import Symbol, Test as DBTest
                session = SessionLocal()
                from sqlalchemy import func
                try:
                    sym_row = session.query(Symbol).filter(
                        (func.lower(Symbol.name) == target_symbol) | 
                        (func.lower(Symbol.qualified_name) == target_symbol)
                    ).first()
                    if sym_row:
                        test_rows = session.query(DBTest).filter(DBTest.target_symbol_id == sym_row.id).all()
                        test_file_ids = [t.file_id for t in test_rows]
                        if test_file_ids:
                            for chunk in self.retriever.chunks:
                                if chunk.get("file_id") in test_file_ids or any(tf in chunk.get("file", "") for tf in test_file_ids):
                                    candidates.append({"score": 100.0, "chunk": chunk})
                                elif "test" in chunk.get("file", "").lower() and target_symbol in chunk.get("file", "").lower():
                                    candidates.append({"score": 90.0, "chunk": chunk})
                except Exception as ex:
                    print(f"[RetrievalPipeline] Graph fast-path query error: {ex}")
                finally:
                    session.close()

                from retrieval.ranker import SpecRanker
                reranked = SpecRanker.rerank_candidates(candidates, context=context)
                return [{"chunk": item["chunk"], "score": item["score"]} for item in reranked[:top_k]]

        # Fallback to Stage 1: Broad recall (Vector search gets candidate pool of top 100 chunks)
        candidates = self.retriever.search(query=query, top_k=100)
        if not candidates:
            return []

        # Stage 2 & 3: Feature enrichment and reranking
        from retrieval.ranker import SpecRanker
        reranked = SpecRanker.rerank_candidates(candidates, context=context)

        # Map back to original structure format (List of {"chunk": chunk, "score": score})
        return [{"chunk": item["chunk"], "score": item["score"]} for item in reranked[:top_k]]

    # =====================================================
    # MAIN / SINGLE-QUERY RETRIEVAL
    # =====================================================

    def retrieve_relevant_chunks(
        self,
        query,
        top_k=8,
        expand_context=True,
        goal=None
    ):
        # Resolve RetrievalContext dynamically from SessionCache
        from context.session_cache import SessionCache
        session_ctx = SessionCache.get_session("default")
        
        context = None
        if session_ctx:
            context = RetrievalContext(
                active_file=session_ctx.active_file,
                open_tabs=session_ctx.open_files,
                active_symbol=session_ctx.recent_symbols[0] if session_ctx.recent_symbols else None,
                recent_files=session_ctx.open_files,
                diagnostics=session_ctx.diagnostics
            )

        # Call retrieve with the resolved context
        results = self.retrieve(query=query, context=context, top_k=top_k * 2)

        if not results:
            return []

        results = self.deduplicate(results)

        if expand_context:
            results = self.expand_neighbors(results)
            results = self.expand_graph_context(results)

        results = self.rerank(query, results, goal=goal)

        return results[:top_k]

    def expand_graph_context(self, results: List[Dict[str, Any]], session=None) -> List[Dict[str, Any]]:
        """
        Database-driven graph expansion.
        For each retrieved chunk containing a symbol or file, find related symbols
        (callers, callees, interfaces, implementations) and tests, and add their chunks.
        """
        if not results:
            return []

        from repository_intelligence.db.connection import SessionLocal
        from repository_intelligence.models.symbol import Symbol, SymbolRelationship, Test as DBTest
        from repository_intelligence.models.file import File
        from sqlalchemy import or_

        db_session = session if session is not None else SessionLocal()
        close_session = True if session is None else False

        expanded_results = list(results)
        existing_chunk_ids = {r["chunk"].get("chunk_id") for r in results if r["chunk"].get("chunk_id")}

        try:
            # 1. Collect symbol names and files from only the top 3 results to limit noise
            symbol_names = set()
            file_paths = set()
            for r in results[:3]:
                chunk = r["chunk"]
                sym = chunk.get("symbol") or chunk.get("name")
                if sym:
                    symbol_names.add(sym)
                f = chunk.get("file")
                if f:
                    file_paths.add(f)

            if not symbol_names and not file_paths:
                return results

            # 2. Retrieve corresponding database symbols
            db_symbols = []
            if symbol_names:
                db_symbols = db_session.query(Symbol).filter(
                    or_(
                        Symbol.name.in_(list(symbol_names)),
                        Symbol.qualified_name.in_(list(symbol_names))
                    )
                ).all()

            symbol_ids = [s.id for s in db_symbols]

            # 3. Retrieve callers, callees, interfaces, implementations
            related_symbol_ids = set()
            if symbol_ids:
                # Direct relationships: USES, EXTENDS, IMPLEMENTS
                relations = db_session.query(SymbolRelationship).filter(
                    or_(
                        SymbolRelationship.source_symbol_id.in_(symbol_ids),
                        SymbolRelationship.target_symbol_id.in_(symbol_ids)
                    )
                ).all()

                for rel in relations:
                    if rel.source_symbol_id and rel.source_symbol_id not in symbol_ids:
                        related_symbol_ids.add(rel.source_symbol_id)
                    if rel.target_symbol_id and rel.target_symbol_id not in symbol_ids:
                        related_symbol_ids.add(rel.target_symbol_id)

            # 4. Query tests associated with target symbols or files
            test_file_paths = set()
            if file_paths:
                # Query tests targeting files by checking files in repository
                db_files = db_session.query(File).filter(File.path.in_(list(file_paths))).all()
                db_file_ids = [f.id for f in db_files]
                if db_file_ids:
                    # Find tests linked to symbols in these files
                    symbols_in_files = db_session.query(Symbol.id).filter(Symbol.file_id.in_(db_file_ids)).all()
                    sym_ids_in_files = [s[0] for s in symbols_in_files]
                    
                    test_records = []
                    if sym_ids_in_files:
                        test_records = db_session.query(DBTest).filter(
                            or_(
                                DBTest.file_id.in_(db_file_ids),
                                DBTest.target_symbol_id.in_(sym_ids_in_files)
                            )
                        ).all()
                    else:
                        test_records = db_session.query(DBTest).filter(DBTest.file_id.in_(db_file_ids)).all()

                    test_file_ids = [t.file_id for t in test_records]
                    if test_file_ids:
                        test_files = db_session.query(File.path).filter(File.id.in_(test_file_ids)).all()
                        for (tf_path,) in test_files:
                            if tf_path:
                                test_file_paths.add(tf_path)

            # 5. Load the related symbols from DB to get their names and files
            related_symbols = []
            if related_symbol_ids:
                related_symbols = db_session.query(Symbol).filter(Symbol.id.in_(list(related_symbol_ids))).all()

            # Group target patterns to search for in our chunk cache
            target_related_names = {s.name for s in related_symbols} | {s.qualified_name for s in related_symbols}
            target_related_files = set()
            for s in related_symbols:
                # Resolve the symbol's file path via the relation/foreign key
                try:
                    s_file = db_session.query(File.path).filter(File.id == s.file_id).first()
                    if s_file and s_file[0]:
                        target_related_files.add(s_file[0])
                except Exception:
                    pass
            target_related_files.update(test_file_paths)

            # 6. Locate matching chunks in retriever chunks
            added_chunks = []
            for chunk in getattr(self.retriever, "chunks", []):
                chunk_id = chunk.get("chunk_id")
                if chunk_id in existing_chunk_ids:
                    continue

                chunk_symbol = chunk.get("symbol") or chunk.get("name")
                chunk_file = chunk.get("file")

                matches_symbol = chunk_symbol and chunk_symbol in target_related_names
                matches_file = chunk_file and chunk_file in target_related_files

                if matches_symbol or matches_file:
                    existing_chunk_ids.add(chunk_id)
                    # Use a scaled score for graph-expanded neighborhood chunks
                    added_chunks.append({
                        "score": 0.5, # base expanded relevance score
                        "chunk": chunk
                    })

            expanded_results.extend(added_chunks)

        except Exception as e:
            print(f"[RetrievalPipeline] Warning: Graph expansion failed: {e}")
        finally:
            if close_session:
                db_session.close()

        return expanded_results

    # =====================================================
    # MULTI-QUERY RETRIEVAL
    # =====================================================

    def retrieve_multi_query(
        self,
        queries,
        top_k=8,
        expand_context=True,
        goal=None
    ):
        """
        Run one FAISS search per query, merge, deduplicate, re-rank.
        Use for complex goals where a single embedding misses related files.
        """
        merged = []
        seen_ids = set()

        for query in queries:
            try:
                results = self.retriever.search(
                    query=query,
                    top_k=top_k
                )
            except Exception as e:
                print(
                    f"[RetrievalPipeline] "
                    f"multi-query search failed "
                    f"for '{query}': {e}"
                )
                continue

            for item in results:
                chunk_id = item["chunk"].get("chunk_id")
                if chunk_id and chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)
                merged.append(item)

        if not merged:
            return []

        if expand_context:
            merged = self.expand_neighbors(merged)

        merged = self.deduplicate(merged)

        primary_query = queries[0] if queries else ""
        merged = self.rerank(primary_query, merged, goal=goal)

        return merged[:top_k]

    # =====================================================
    # HIERARCHICAL RETRIEVAL
    # =====================================================

    def retrieve_hierarchical(
        self,
        query,
        top_k=8,
        queries=None,
        goal=None
    ):
        """
        Cascading retrieval: file → class → method → chunk.
        Falls back to flat multi-query if hierarchical index not available.
        """
        hier_retriever = getattr(
            self.retriever, "hierarchical_index", None
        )

        if hier_retriever is None or getattr(hier_retriever, "store", None) is None:
            # Fall back to flat retrieval
            if queries:
                return self.retrieve_multi_query([query] + queries, top_k=top_k, goal=goal)
            return self.retrieve_relevant_chunks(query, top_k=top_k, goal=goal)

        try:
            from retrieval.hierarchy.hierarchical_retriever import (
                HierarchicalRetriever
            )
            h_retriever = HierarchicalRetriever(
                store=hier_retriever.store,
                embedding_engine=self.retriever.embedding_engine,
            )

            if queries:
                results = h_retriever.search_multi(
                    [query] + queries, top_k=top_k
                )
            else:
                results = h_retriever.search(query, top_k=top_k)

            # Expand neighbors using flat chunk graph
            results = self.expand_neighbors(results)
            results = self.deduplicate(results)
            results = self.rerank(query, results, goal=goal)
            return results[:top_k]

        except Exception as e:
            print(f"[RetrievalPipeline] Hierarchical retrieval failed: {e} — falling back")
            if queries:
                return self.retrieve_multi_query([query] + queries, top_k=top_k, goal=goal)
            return self.retrieve_relevant_chunks(query, top_k=top_k, goal=goal)

    # =====================================================
    # DEPENDENCY EXPANSION
    # =====================================================

    def expand_by_dependency(
        self,
        results,
        depth=1,
    ):
        """
        Use the DependencyGraph to add callers and callees of the matched files.
        Dependency-expanded chunks get a slightly reduced score (0.85×).
        """
        dep_graph = getattr(self.retriever, "dependency_graph", None)
        if dep_graph is None:
            return results

        matched_files = {item["chunk"].get("file") for item in results}
        extra_files = set()

        for file_path in matched_files:
            if not file_path:
                continue
            extra_files.update(dep_graph.neighborhood(file_path, depth=depth))

        extra_files -= matched_files  # don't re-add already-matched

        # Find chunks that belong to the dependency neighborhood
        extra_chunks = [
            chunk for chunk in self.retriever.chunks
            if chunk.get("file") in extra_files
        ]

        # Deduplicate by chunk_id against existing results
        existing_ids = {item["chunk"].get("chunk_id") for item in results}
        added = []
        for chunk in extra_chunks:
            cid = chunk.get("chunk_id")
            if cid not in existing_ids:
                existing_ids.add(cid)
                added.append({"score": 0.5, "chunk": chunk})  # lower score for deps

        return results + added

    # =====================================================
    # DEDUPLICATION
    # =====================================================

    def deduplicate(
        self,
        results
    ):
        seen = set()
        deduped = []

        for item in results:
            chunk = item["chunk"]
            key = chunk.get(
                "chunk_id"
            )

            if key in seen:
                continue

            seen.add(key)
            deduped.append(item)

        return deduped

    # =====================================================
    # CONTEXT EXPANSION
    # =====================================================

    def expand_neighbors(
        self,
        results
    ):
        expanded = []
        lookup = defaultdict(list)

        for chunk in self.retriever.chunks:
            lookup[
                chunk["file"]
            ].append(chunk)

        for item in results:
            expanded.append(item)
            chunk = item["chunk"]
            current_index = chunk.get(
                "chunk_index",
                0
            )

            siblings = lookup[
                chunk["file"]
            ]

            for sibling in siblings:
                sibling_index = sibling.get(
                    "chunk_index",
                    0
                )

                if abs(
                    sibling_index
                    - current_index
                ) <= 1:
                    expanded.append({
                        "score":
                            item["score"] * 0.92,
                        "chunk":
                            sibling
                    })

        return expanded

    # =====================================================
    # RERANK
    # =====================================================

    def rerank(
        self,
        query,
        results,
        goal=None
    ):
        query_lower = query.lower()

        for item in results:
            chunk = item["chunk"]
            score = item["score"]

            # =============================================
            # SYMBOL BOOST
            # =============================================
            if query_lower in chunk.get(
                "name",
                ""
            ).lower():
                score += 0.20

            # =============================================
            # FILE BOOST
            # =============================================
            if query_lower in chunk.get(
                "file",
                ""
            ).lower():
                score += 0.15

            # =============================================
            # DOCSTRING BOOST
            # =============================================
            if query_lower in chunk.get(
                "docstring",
                ""
            ).lower():
                score += 0.10

            # =============================================
            # PARENT BOOST
            # =============================================
            if query_lower in str(
                chunk.get("parent", "")
            ).lower():
                score += 0.08

            # =============================================
            # LEVEL BOOST (method/class precision)
            # =============================================
            level = chunk.get("level", 4)
            if level == 3:   # method
                score += 0.05
            elif level == 2: # class
                score += 0.03

            item["score"] = score

        # Apply enterprise hybrid ranking layer
        return self.ranking_engine.rank(query, results, context={"goal": goal})
