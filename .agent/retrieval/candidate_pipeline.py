# retrieval/candidate_pipeline.py
#
# Two-Stage Retrieval Pipeline (Cursor Architecture)
#
# Stage 1: Multi-channel candidate generation
#   - ANN semantic search (FAISS HNSW, top 100)
#   - Symbol index lookup (exact + partial matches)
#   - BM25 lexical search (top 50)
#
# Stage 2: Semantic confidence filter + gated reranking
#   - Compute semantic confidence per candidate
#   - Hard filter weak matches (confidence < 0.35)
#   - Penalize generic utility files
#   - Rerank with relevance-dominant weights
#   - Optional cross-encoder reranking (top 30)

import re
import time
from typing import List, Dict, Any, Optional


# Generic utility file patterns that attract false positives
GENERIC_PATTERNS = [
    r"(?i)utils?\.(?:java|py|ts|js)$",
    r"(?i)specification[s]?\.(?:java|py|ts|js)$",
    r"(?i)constant[s]?\.(?:java|py|ts|js)$",
    r"(?i)config\.(?:java|py|ts|js)$",
    r"(?i)base[a-z]*\.(?:java|py|ts|js)$",
    r"(?i)abstract[a-z]*\.(?:java|py|ts|js)$",
    r"(?i)helper[s]?\.(?:java|py|ts|js)$",
    r"(?i)common[s]?\.(?:java|py|ts|js)$",
]

_GENERIC_RE = [re.compile(p) for p in GENERIC_PATTERNS]


def _is_generic_file(file_path: str) -> bool:
    """Check if a file path matches known generic utility patterns."""
    if not file_path:
        return False
    basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    return any(pat.search(basename) for pat in _GENERIC_RE)


class CandidatePipeline:
    """
    Two-stage retrieval pipeline that separates candidate generation
    from reranking to achieve Cursor-level retrieval quality.
    """

    def __init__(self, ann_backend=None, bm25_index=None, symbol_index=None, cross_encoder=None, pgvector_retriever=None, vector_store=None):
        self.ann_backend = ann_backend or pgvector_retriever or vector_store
        self.bm25_index = bm25_index
        self.symbol_index = symbol_index
        self.cross_encoder = cross_encoder

    def retrieve(
        self,
        query: str,
        query_embedding=None,
        top_k: int = 20,
        intent: str = None,
        session=None
    ) -> List[Dict[str, Any]]:
        """
        Full two-stage retrieval pipeline.
        
        Stage 1: Multi-channel candidate generation
        Stage 2: Semantic filter → generic penalty → gated rerank → cross-encoder
        """
        start = time.time()

        # ── Stage 1: Candidate Generation ──────────────────────────
        candidates = {}  # chunk_id -> best candidate dict

        # Channel A: pgvector ANN semantic search (top 50)
        if self.ann_backend and query_embedding is not None:
            # Dynamically extract pre-filters from query context
            from context.session_cache import SessionCache
            from retrieval.pgvector_backend import extract_filters
            
            active_file = None
            try:
                session_ctx = SessionCache.get_session("default")
                if session_ctx:
                    active_file = session_ctx.active_file
            except Exception:
                pass

            filters = extract_filters(query, active_file)
            
            # Use search with pre-filters on the new pgvector backend
            ann_results = self.ann_backend.search(query_embedding, k=50, filters=filters)
            
            for item in ann_results:
                cid = item["chunk_id"]
                # Convert the database candidate back to a chunk structure compatible with the rest of the pipeline
                chunk = {
                    "chunk_id": item["chunk_id"],
                    "file": item["file_path"],
                    "symbol": item["symbol"],
                    "symbol_path": item["symbol_path"],
                    "content": item["content"],
                    "code": item["content"],
                    "start_line": item["start_line"],
                    "end_line": item["end_line"],
                    "imports": item["imports"] or []
                }
                score = item["semantic_score"]
                if cid not in candidates or score > candidates[cid].get("ann_score", 0):
                    candidates[cid] = {
                        "chunk": chunk,
                        "ann_score": float(score),
                        "symbol_score": 0.0,
                        "bm25_score": 0.0
                    }
                else:
                    candidates[cid]["ann_score"] = max(
                        candidates[cid].get("ann_score", 0), float(score)
                    )

        # Resolve target roots for workspace routing filter
        from context.session_cache import SessionCache
        from retrieval.workspace_router import classify_workspace_target
        active_file = None
        try:
            session_ctx = SessionCache.get_session("default")
            if session_ctx:
                active_file = session_ctx.active_file
        except Exception:
            pass
        target_roots = classify_workspace_target(query, active_file)

        # Channel B: Symbol index lookup
        if self.symbol_index:
            from retrieval.symbol_index import extract_symbols
            symbols = extract_symbols(query)
            if symbols:
                sym_results = self.symbol_index.lookup(symbols, k=50)
                for item in sym_results:
                    fpath = item["chunk"].get("file", "")
                    if target_roots and not any(fpath.startswith(r) for r in target_roots):
                        continue
                    cid = self._chunk_id(item["chunk"])
                    if cid not in candidates:
                        candidates[cid] = {
                            "chunk": item["chunk"],
                            "ann_score": 0.0,
                            "symbol_score": float(item["score"]),
                            "bm25_score": 0.0
                        }
                    else:
                        candidates[cid]["symbol_score"] = max(
                            candidates[cid].get("symbol_score", 0), float(item["score"])
                        )

        # Channel C: BM25 lexical search (top 50)
        if self.bm25_index:
            bm25_results = self.bm25_index.search(query, k=50)
            for item in bm25_results:
                fpath = item["chunk"].get("file", "")
                if target_roots and not any(fpath.startswith(r) for r in target_roots):
                    continue
                cid = self._chunk_id(item["chunk"])
                if cid not in candidates:
                    candidates[cid] = {
                        "chunk": item["chunk"],
                        "ann_score": 0.0,
                        "symbol_score": 0.0,
                        "bm25_score": float(item["score"])
                    }
                else:
                    candidates[cid]["bm25_score"] = max(
                        candidates[cid].get("bm25_score", 0), float(item["score"])
                    )

        if not candidates:
            return []

        # ── Stage 2: Filter + Rerank ───────────────────────────────

        # Step 1: Compute semantic confidence per candidate
        scored = []
        for cid, cand in candidates.items():
            confidence = max(
                cand["ann_score"],
                cand["symbol_score"],
                cand["bm25_score"]
            )
            cand["confidence"] = confidence
            scored.append(cand)

        # Step 2: Hard filter weak semantic matches
        threshold = 0.55
        filtered = [c for c in scored if c["confidence"] >= threshold]

        # If too aggressive, relax threshold to preserve at least a minimal candidate pool
        if len(filtered) < 3 and len(scored) > 3:
            threshold = 0.20
            filtered = [c for c in scored if c["confidence"] >= threshold]
        if not filtered:
            filtered = sorted(scored, key=lambda x: x["confidence"], reverse=True)[:top_k]

        # Step 3: Penalize generic utility files
        for cand in filtered:
            fpath = cand["chunk"].get("file", "")
            if _is_generic_file(fpath):
                cand["ann_score"] *= 0.85
                cand["bm25_score"] *= 0.85
                cand["confidence"] *= 0.85

        # Step 4: Gated reranking — structure-first weights
        #
        # Philosophy: CandidatePipeline is only reached as SEMANTIC fallback
        # (after SYMBOL and GRAPH routes have already failed). Even here, we
        # bias heavily toward structural signals over probabilistic embeddings.
        #
        #   symbol  0.45  — deterministic, exact match → highest authority
        #   graph   0.35  — structural neighborhood (imports, deps) → high authority
        #   semantic 0.10 — probabilistic ANN embedding → supporting signal only
        #   path    0.05  — file path domain heuristic
        #   history 0.05  — recent edits / active file / open tabs
        w_semantic = 0.10
        w_symbol   = 0.45
        w_path     = 0.05
        w_graph    = 0.35
        w_history  = 0.05

        # Resolve history context from SessionCache dynamically
        active_file = None
        open_tabs = []
        try:
            from context.session_cache import SessionCache
            session_ctx = SessionCache.get_session("default")
            if session_ctx:
                active_file = session_ctx.active_file
                open_tabs = session_ctx.open_files or []
        except Exception:
            pass

        for cand in filtered:
            chunk = cand["chunk"]
            
            # 1. Semantic score
            semantic_score = cand["ann_score"]
            
            # 2. Symbol score (boost if query mentions class, query mentions method, or symbol_path matches)
            symbol_score = self._compute_symbol_score(query, chunk)
            if cand["symbol_score"] > 0:
                symbol_score = max(symbol_score, cand["symbol_score"])
                
            # 3. Path score (boost if file path matches domain)
            path_score = self._compute_path_relevance(query, chunk.get("file", ""))
            
            # 4. Graph score (imported classes / dependencies)
            graph_score = self._compute_graph_score(query, chunk)
            
            # 5. History score (recent edits / active files / open tabs)
            history_score = self._compute_history_score(chunk, active_file, open_tabs)

            # Apply Role-weighted retrieval weight (P0 index pollution guard)
            role_weight = 1.0
            try:
                from repository_intelligence.indexer.file_classifier import FileClassifier, FileRole
                from pathlib import Path
                filepath = Path(chunk.get("file", ""))
                decision = FileClassifier.classify(filepath, Path(""))
                
                ROLE_WEIGHTS = {
                    FileRole.SOURCE: 1.0,
                    FileRole.TEST: 0.3,
                    FileRole.CONFIG: 0.8,
                    FileRole.DOC: 0.5,
                    FileRole.GENERATED: 0.05,
                    FileRole.BUILD_ARTIFACT: 0.0,
                    FileRole.AGENT_STATE: 0.0,
                    FileRole.BINARY: 0.0,
                    FileRole.CACHE: 0.0
                }
                role_weight = ROLE_WEIGHTS.get(decision.role, 1.0)
            except Exception as e:
                print(f"[CandidatePipeline] Role weighting warning: {e}")

            cand["final_score"] = (
                semantic_score * w_semantic
                + symbol_score * w_symbol
                + path_score * w_path
                + graph_score * w_graph
                + history_score * w_history
            ) * role_weight
            
            # Store ranking diagnostics for debugging
            chunk["_ranking_diagnostics"] = {
                "semantic_score": float(semantic_score),
                "symbol_score": float(symbol_score),
                "path_score": float(path_score),
                "graph_score": float(graph_score),
                "history_score": float(history_score),
                "role_weight": float(role_weight),
                "final_score": float(cand["final_score"])
            }

        # ── Fix: Symbol Canonicalization and Duplicate Collapse ──────
        symbol_groups = {}
        for cand in filtered:
            chunk = cand["chunk"]
            sym_path = chunk.get("symbol_path") or chunk.get("symbol")
            sym_id = sym_path if sym_path else chunk.get("file", "")
            symbol_groups.setdefault(sym_id, []).append(cand)
            
        collapsed_filtered = []
        for sym_id, group in symbol_groups.items():
            # Sort within group: prioritize canonical, then highest final_score
            def sort_key(c):
                filepath = Path(c["chunk"].get("file", ""))
                try:
                    from repository_intelligence.indexer.file_classifier import FileClassifier, FileRole
                    decision = FileClassifier.classify(filepath, Path(""))
                    is_canonical = (decision.role in (FileRole.SOURCE, FileRole.TEST, FileRole.CONFIG, FileRole.DOC))
                except Exception:
                    is_canonical = True
                return (1 if is_canonical else 0, c.get("final_score", 0.0))
                
            group.sort(key=sort_key, reverse=True)
            best_cand = group[0]
            
            # Apply duplicate penalty if multiple representations exist and chosen one is not canonical
            num_variants = len(group)
            if num_variants > 1:
                filepath = Path(best_cand["chunk"].get("file", ""))
                try:
                    from repository_intelligence.indexer.file_classifier import FileClassifier, FileRole
                    decision = FileClassifier.classify(filepath, Path(""))
                    is_canonical = (decision.role in (FileRole.SOURCE, FileRole.TEST, FileRole.CONFIG, FileRole.DOC))
                except Exception:
                    is_canonical = True
                    
                if not is_canonical:
                    best_cand["final_score"] *= (1.0 / num_variants)
                    
            collapsed_filtered.append(best_cand)
            
        filtered = collapsed_filtered

        # Sort by final score
        filtered.sort(key=lambda x: x["final_score"], reverse=True)

        # Step 5: Cross-encoder reranking (top 30 → top_k)
        top_candidates = filtered[:30]
        if self.cross_encoder and hasattr(self.cross_encoder, 'available') and self.cross_encoder.available:
            reranked_items = [{"score": c["final_score"], "chunk": c["chunk"]} for c in top_candidates]
            try:
                reranked_items = self.cross_encoder.rerank(query, reranked_items, k=top_k)
                # Ensure cross-encoder also preserves diagnostics
                for item in reranked_items:
                    for tc in top_candidates:
                        if self._chunk_id(tc["chunk"]) == self._chunk_id(item["chunk"]):
                            item["chunk"]["_ranking_diagnostics"] = tc["chunk"]["_ranking_diagnostics"]
                            break
                elapsed = time.time() - start
                print(f"[CandidatePipeline] Two-stage retrieval completed in {elapsed:.3f}s "
                      f"(candidates={len(candidates)}, filtered={len(filtered)}, cross-encoded)")
                return reranked_items
            except Exception as e:
                print(f"[CandidatePipeline] Cross-encoder reranking failed: {e}")

        # Format output
        results = []
        for cand in top_candidates[:top_k]:
            results.append({
                "score": cand["final_score"],
                "chunk": cand["chunk"]
            })

        elapsed = time.time() - start
        
        # Emit retrieval_completed event
        try:
            from context.session_cache import SessionCache
            from observability.event_bus import EventBus
            session = SessionCache.get_session("default")
            active_file = session.active_file
            req_id = session.task_id or "unknown"
            
            # Compute hit position
            hit_rank = 0
            for i, cand in enumerate(results):
                if cand["chunk"].get("file") == active_file:
                    hit_rank = i + 1
                    break
                    
            total_cand = len(candidates)
            collapsed_cand = len(filtered)
            dup_ratio = (total_cand - collapsed_cand) / total_cand if total_cand > 0 else 0.0
            
            EventBus().emit(
                event_type="retrieval_completed",
                request_id=req_id,
                payload={
                    "query": query,
                    "hit_rank": hit_rank,
                    "duplicate_candidate_ratio": dup_ratio
                }
            )
        except Exception:
            pass

        print(f"[CandidatePipeline] Two-stage retrieval completed in {elapsed:.3f}s "
              f"(candidates={len(candidates)}, filtered={len(filtered)})")
        return results

    def _chunk_id(self, chunk: dict) -> str:
        """Generate a stable identifier for deduplication."""
        symbol = chunk.get("symbol") or chunk.get("name") or ""
        fpath = chunk.get("file") or ""
        start = chunk.get("start_line") or chunk.get("line") or 0
        return f"{fpath}::{symbol}::{start}"

    def _compute_path_relevance(self, query: str, file_path: str) -> float:
        """Compute path relevance score between query tokens and file path."""
        if not file_path or not query:
            return 0.0

        # Extract meaningful tokens from query
        words = re.findall(r'\b\w+\b', query.lower())
        query_tokens = set()
        for w in words:
            if len(w) > 2:
                query_tokens.add(w)
            # Split camelCase
            parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', w)
            for p in parts:
                if len(p) > 2:
                    query_tokens.add(p.lower())

        if not query_tokens:
            return 0.0

        fpath_lower = file_path.lower()
        matches = sum(1 for t in query_tokens if t in fpath_lower)
        return min(1.0, matches * 0.25)

    def _compute_symbol_score(self, query: str, chunk: dict) -> float:
        """Boost if query mentions class, query mentions method, or symbol_path matches."""
        q_lower = query.lower()
        symbol = (chunk.get("symbol") or chunk.get("name") or "").lower()
        symbol_path = (chunk.get("symbol_path") or "").lower()
        
        if not symbol:
            return 0.0
            
        # Extract CamelCase targets from query (e.g. EmployeeService)
        camel_case = [t.lower() for t in re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', query)]
        
        # 1. Exact match of symbol name with any target
        for target in camel_case:
            if symbol == target:
                return 1.0
                
        # 2. Substring match: target is in symbol (e.g. "employeeservice" is in "employeeserviceimpl")
        for target in camel_case:
            if len(target) >= 6 and target in symbol:
                return 0.80
                
        # 3. Path match
        if symbol_path:
            for target in camel_case:
                if len(target) >= 6 and target in symbol_path:
                    return 0.60
                    
        # 4. Symbol is in query
        if symbol in q_lower:
            return 0.50

        # 5. Sub-word matches (lower boost to prevent false positives like EmployeeSpecifications)
        sub_words = []
        for token in camel_case:
            parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', token)
            sub_words.extend([p.lower() for p in parts if len(p) > 3])
            
        for sw in sub_words:
            if sw in symbol:
                return 0.10  # low match boost to prevent specifications from winning
                
        return 0.0

    def _compute_graph_score(self, query: str, chunk: dict) -> float:
        """Use symbol graph dependencies (imported classes, references, callers/callees)."""
        q_lower = query.lower()
        imports = chunk.get("imports") or []
        
        # Boost if query mentions any imported symbols/packages
        match_count = 0
        for imp in imports:
            short_name = imp.split(".")[-1]
            if len(short_name) > 2 and short_name.lower() in q_lower:
                match_count += 1
                
        if match_count > 0:
            return min(1.0, match_count * 0.50)
            
        return 0.0

    def _compute_history_score(self, chunk: dict, active_file: Optional[str], open_tabs: List[str]) -> float:
        """Use runtime memory: recent edits, active files, open tabs."""
        file_path = chunk.get("file") or ""
        if not file_path:
            return 0.0
            
        # Active file boost
        if active_file and (file_path in active_file or active_file in file_path):
            return 1.0
            
        # Open tabs boost
        for tab in open_tabs:
            if tab and (file_path in tab or tab in file_path):
                return 0.50
                
        return 0.0
