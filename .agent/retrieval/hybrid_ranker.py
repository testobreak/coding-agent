# retrieval/hybrid_ranker.py
#
# Enterprise cognitive multi-signal retrieval ranker.
# Sorts candidates based on a composite formula of 7 specific signals:
#   Final Score =
#       symbol_score     * 0.35 +
#       graph_score      * 0.20 +
#       embedding_score  * 0.15 +
#       path_score       * 0.10 +
#       impact_score     * 0.10 +
#       test_score       * 0.05 +
#       historical_score * 0.05
#

import os
import sys
import re
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import text

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.repository import Repository
from repository_intelligence.models.file import File
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.symbol import Test as DBTest
from retrieval.symbol_graph_cache import SymbolGraphCache


class RetrievalCandidate:
    """
    Representation of a retrieval candidate containing explicit signal scores.
    """
    def __init__(self, item: Dict[str, Any]):
        self.item = item
        self.chunk = item.get("chunk", {})
        
        # Explicit signal scores
        self.embedding_score = 0.0
        self.symbol_score = 0.0
        self.graph_score = 0.0
        self.path_score = 0.0
        self.impact_score = 0.0
        self.test_score = 0.0
        self.historical_score = 0.0
        self.lexical_score = 0.0
        
        self.final_score = 0.0


class HybridRanker:
    """
    Next-Level Enterprise Multi-Signal Retrieval Ranker.
    """
    def __init__(self, cross_encoder=None):
        # Specific weights requested by the user
        self.symbol_weight = 0.25
        self.graph_weight = 0.10
        self.embedding_weight = 0.45
        self.path_weight = 0.15
        self.impact_weight = 0.0
        self.test_weight = 0.0
        self.historical_weight = 0.05

        # Accept injected cross-encoder (lazy-loaded via ModelService)
        # If none provided, create one using legacy path (will load on first rerank call)
        self._cross_encoder = cross_encoder

    @property
    def cross_encoder(self):
        """Return injected cross-encoder or lazy-create a legacy one."""
        if self._cross_encoder is None:
            from retrieval.cross_encoder import CrossEncoderReranker
            self._cross_encoder = CrossEncoderReranker()  # legacy path, lazy
        return self._cross_encoder


    def extract_target_symbols(self, query: str) -> List[str]:
        """
        Zero-latency heuristic extractor capturing camel-cased symbol tokens
        or dotted namespaces from the query.
        """
        # CamelCase tokens (e.g. EmployeeService, EmployeeController)
        camel_case = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', query)
        # Dotted namespace paths (e.g. com.example.EmployeeService)
        dotted = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_\.]*\.[A-Z][a-zA-Z0-9_]*\b', query)
        
        # Split CamelCase tokens into sub-words
        sub_words = []
        for token in camel_case:
            parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', token)
            sub_words.extend(parts)
            
        return list(set(camel_case + dotted + sub_words))

    def rank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        context: Dict[str, Any] = None,
        session=None
    ) -> List[Dict[str, Any]]:
        """
        Ranks the candidates list using the 7-signal enterprise formula.
        """
        if not candidates:
            return []

        # Filter ignore patterns unless query explicitly asks about tests/mocks/verification
        query_lower = query.lower()
        needs_tests = any(x in query_lower for x in ["test", "spec", "mock", "verify"])
        if not needs_tests:
            filtered_candidates = []
            for item in candidates:
                chunk = item.get("chunk", {})
                f = (chunk.get("file") or "").lower()
                if any(pat in f for pat in ["/tests/", "verify_", "mock", "_test.py"]):
                    continue
                filtered_candidates.append(item)
            candidates = filtered_candidates

        if not candidates:
            return []

        # Resolve DB session
        if session is None:
            db_session = SessionLocal()
            close_session = True
        else:
            db_session = session
            close_session = False

        ranked_items = []

        try:
            # 1. Parse intent target symbols
            targets = self.extract_target_symbols(query)
            
            # 2. Get active task_id safely for historical scoring
            task_id = "unknown_task"
            if context and context.get("task_id"):
                task_id = context.get("task_id")
            
            # Batch retrieve database metadata for candidates to optimize performance
            file_paths = {c["chunk"].get("file") for c in candidates if c["chunk"].get("file")}
            symbol_names = {
                c["chunk"].get("symbol") or c["chunk"].get("name")
                for c in candidates
                if c["chunk"].get("symbol") or c["chunk"].get("name")
            }

            db_files = {}
            if file_paths:
                rows = db_session.query(File).filter(File.path.in_(list(file_paths))).all()
                db_files = {f.path: f for f in rows}

            db_symbols = {}
            if symbol_names:
                rows = db_session.query(Symbol).filter(
                    Symbol.qualified_name.in_(list(symbol_names)) |
                    Symbol.name.in_(list(symbol_names))
                ).all()
                for s in rows:
                    db_symbols[s.qualified_name] = s
                    db_symbols[s.name] = s

            # Fetch committed files historically
            committed_files = []
            try:
                res = db_session.execute(
                    text("SELECT modified_files FROM modification_checkpoints WHERE validation_status = 'COMMITTED'")
                ).fetchall()
                for r in res:
                    if r[0]:
                        if isinstance(r[0], list):
                            committed_files.extend(r[0])
                        elif isinstance(r[0], str):
                            val = r[0].strip()
                            if val.startswith('{') and val.endswith('}'):
                                files = [f.strip() for f in val[1:-1].split(',') if f.strip()]
                                committed_files.extend(files)
                            elif val.startswith('[') and val.endswith(']'):
                                import json
                                try:
                                    files = json.loads(val)
                                    if isinstance(files, list):
                                        committed_files.extend(files)
                                except Exception:
                                    pass
                            else:
                                committed_files.extend([f.strip() for f in val.split(',') if f.strip()])
            except Exception as e:
                print(f"[HybridRanker] Checkpoint scan skipped: {e}")

            from retrieval.query_intent import RetrievalIntentClassifier, RetrievalIntent
            intent = RetrievalIntentClassifier.classify(query)

            # ── Structure-first weights (Cursor architecture) ───────────────
            #
            # Semantic reduced from 0.45 → 0.35 across all code-action intents.
            # Reason: embeddings alone produce false positives when symbol and
            # path scores are 0 but embedding score is 37-42 (confirmed in
            # ranking diagnostics).  Symbol + path encode structural certainty
            # that embeddings cannot.
            #
            # EXPLAIN keeps slightly higher semantic (0.40) because it is a
            # natural-language task, not a surgical edit target.

            if intent == RetrievalIntent.MODIFY_SYMBOL or intent == RetrievalIntent.BUG_FIX:
                w_semantic = 0.35
                w_symbol   = 0.30
                w_path     = 0.20
                w_graph    = 0.10
                w_history  = 0.05
            elif intent == RetrievalIntent.REFACTOR:
                w_semantic = 0.35
                w_symbol   = 0.30
                w_path     = 0.20
                w_graph    = 0.10
                w_history  = 0.05
            elif intent == RetrievalIntent.EXPLAIN:
                w_semantic = 0.40
                w_symbol   = 0.25
                w_path     = 0.20
                w_graph    = 0.10
                w_history  = 0.05
            else:  # SEARCH / DEFAULT
                w_semantic = 0.35
                w_symbol   = 0.30
                w_path     = 0.20
                w_graph    = 0.10
                w_history  = 0.05

            for item in candidates:
                cand = RetrievalCandidate(item)
                chunk = cand.chunk

                fpath = chunk.get("file")
                file_row = db_files.get(fpath) if fpath else None

                sname = chunk.get("symbol") or chunk.get("name")
                symbol_row = db_symbols.get(sname) if sname else None

                # Calculate raw signals (normalized to 0 - 100 range)
                cand.embedding_score = self.compute_embedding_score(item)
                cand.symbol_score = self.compute_symbol_score(targets, chunk, symbol_row)
                cand.lexical_score = self.compute_lexical_score(query, chunk)
                cand.path_score = self.compute_path_score(query, fpath)
                cand.graph_score = self.compute_graph_score(db_session, symbol_row, targets)
                cand.historical_score = self.compute_historical_score(fpath, committed_files)
                cand.impact_score = self.compute_impact_score(db_session, symbol_row, file_row, targets)
                cand.test_score = self.compute_test_score(db_session, symbol_row, file_row, targets)

                # Normalize components to [0, 1] range for Cursor compatibility
                semantic = cand.embedding_score / 100.0
                symbol = cand.symbol_score / 100.0
                path = cand.path_score / 100.0
                graph = cand.graph_score / 100.0
                history = cand.historical_score / 100.0
                impact = cand.impact_score / 100.0
                test = cand.test_score / 100.0

                # Compute final score using the intent-dynamic weights
                cand.final_score = (
                    semantic     * w_semantic
                    + symbol     * w_symbol
                    + path       * w_path
                    + graph      * w_graph
                    + history    * w_history
                )

                # Apply exact symbol match boost (Cursor-like boosting)
                if cand.symbol_score == 100.0:
                    cand.final_score += 4.0

                # Save metrics in chunk for transparency and logging
                chunk["_ranking_diagnostics"] = {
                    "symbol": cand.symbol_score,
                    "graph": cand.graph_score,
                    "embedding": cand.embedding_score,
                    "path": cand.path_score,
                    "lexical": cand.lexical_score,
                    "recency": cand.historical_score,
                    "impact": cand.impact_score,
                    "test": cand.test_score
                }

                # Convert final score back to 0-100 range for display/compatibility
                item["score"] = cand.final_score * 100.0
                ranked_items.append(item)

        except Exception as e:
            print(f"[HybridRanker] Enterprise ranking encountered error: {e}")
            # Soft fallback
            return sorted(candidates, key=lambda x: x.get("score", 0.0), reverse=True)
        finally:
            if close_session:
                db_session.close()

        # Sort descending by composite score
        sorted_candidates = sorted(ranked_items, key=lambda x: x.get("score", 0.0), reverse=True)

        # Apply local cross-encoder reranking on top 30 candidates to improve correctness
        if self.cross_encoder and getattr(self.cross_encoder, "available", False):
            top_30 = sorted_candidates[:30]
            rest = sorted_candidates[30:]
            
            # Store original scores for blending
            for item in top_30:
                item["score_before_ce"] = item["score"]
                
            try:
                # self.cross_encoder.rerank rescored candidates descendingly
                reranked_top_30 = self.cross_encoder.rerank(query, top_30, k=len(top_30))
                
                # Blend cross-encoder score and hybrid score
                import math
                for item in reranked_top_30:
                    raw_score = item["score"] # Logit score from cross-encoder
                    try:
                        sig_score = 1.0 / (1.0 + math.exp(-raw_score))
                    except OverflowError:
                        sig_score = 0.0 if raw_score < 0 else 1.0
                    
                    orig_score_norm = item.get("score_before_ce", 0.0) / 100.0
                    
                    # If orig_score_norm was boosted (i.e. >= 4.0), remove the boost for blending
                    is_boosted = False
                    if orig_score_norm >= 4.0:
                        orig_score_norm -= 4.0
                        is_boosted = True
                    
                    # Blend: 60% semantic cross-encoder, 40% metadata/hybrid signals
                    blended = 0.60 * sig_score + 0.40 * orig_score_norm
                    item["score"] = blended * 100.0
                    
                    # Apply boost after blending
                    if is_boosted:
                        item["score"] += 400.0
                    
                    # Save metrics for transparency
                    chunk = item.get("chunk", {})
                    if "_ranking_diagnostics" in chunk:
                        chunk["_ranking_diagnostics"]["cross_encoder_score"] = raw_score
                        chunk["_ranking_diagnostics"]["cross_encoder_sig_score"] = sig_score
                        chunk["_ranking_diagnostics"]["blended_score"] = item["score"]
                
                # Sort the blended top 30 again
                reranked_top_30.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                sorted_candidates = reranked_top_30 + rest
            except Exception as e:
                print(f"[HybridRanker] Cross-encoder reranking failed: {e}")

        return sorted_candidates

    def compute_embedding_score(self, item: Dict[str, Any]) -> float:
        score = item.get("score", 0.0)
        # Normalize FAISS score to range [0.0, 1.0] and scale to 100
        normalized = max(0.0, min(1.0, score))
        return normalized * 100.0

    def compute_symbol_score(self, targets: List[str], chunk: Dict[str, Any], symbol: Symbol | None) -> float:
        if not targets:
            return 0.0

        chunk_name = (chunk.get("name") or "").lower()
        chunk_symbol = (chunk.get("symbol") or "").lower()
        symbol_fqn = (symbol.qualified_name.lower() if symbol else "").lower()

        # First pass: Check for exact match with target tokens
        for target in targets:
            target_lower = target.lower()
            if chunk_name == target_lower or chunk_symbol == target_lower or (symbol and symbol.name.lower() == target_lower):
                return 100.0
            if symbol_fqn == target_lower or symbol_fqn.endswith("." + target_lower):
                return 100.0

        # Second pass: Check for target substring match (e.g. "employeeservice" is in "employeeserviceimpl")
        for target in targets:
            target_lower = target.lower()
            # Only allow substring match boost for full camel-case/longer target terms
            if len(target_lower) >= 6:
                if target_lower in chunk_name or target_lower in chunk_symbol or (symbol and target_lower in symbol.name.lower()):
                    return 80.0
                if symbol_fqn and target_lower in symbol_fqn:
                    return 80.0

        # Third pass: Generic sub-word matches (like "Employee" or "Service")
        for target in targets:
            target_lower = target.lower()
            if len(target_lower) > 3:
                if target_lower in chunk_name or target_lower in chunk_symbol or (symbol and target_lower in symbol.name.lower()):
                    return 10.0  # low penalty boost for common subwords

        return 0.0

    def compute_graph_score(self, session, symbol: Symbol | None, targets: List[str]) -> float:
        if not symbol or not targets:
            return 0.0

        cache = SymbolGraphCache.get_instance()
        cache.load(session=session)

        # Resolve target IDs from in-memory index
        target_ids = []
        for t in targets:
            sym = cache.get_symbol_by_qualified_name(t)
            if sym:
                target_ids.append(sym["id"])
            else:
                for sym in cache.get_symbols_by_name(t):
                    target_ids.append(sym["id"])

        if symbol and target_ids:
            for rel in cache.relationships_by_source.get(str(symbol.id), []):
                if rel["target_symbol_id"] in target_ids:
                    return 100.0
            for rel in cache.relationships_by_target.get(str(symbol.id), []):
                if rel["source_symbol_id"] in target_ids:
                    return 100.0

        # Fallback to normalized centrality density
        inbound = len(cache.relationships_by_target.get(str(symbol.id), [])) if symbol else 0
        outbound = len(cache.relationships_by_source.get(str(symbol.id), [])) if symbol else 0
        return min(100.0, (inbound + outbound) * 10.0)

    def compute_path_score(self, query: str, file_path: str) -> float:
        if not file_path or not query:
            return 0.0

        # Extract segments > 3 characters from query
        words = re.findall(r'\b\w+\b', query)
        query_segments = set()
        for w in words:
            if len(w) > 3:
                query_segments.add(w.lower())
            # Split camelCase / PascalCase into sub-words
            sub_words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', w)
            for sw in sub_words:
                if len(sw) > 3:
                    query_segments.add(sw.lower())

        if not query_segments:
            return 0.0

        file_path_lower = file_path.lower()
        matches = sum(1 for seg in query_segments if seg in file_path_lower)
        return min(100.0, matches * 25.0)

    def compute_impact_score(self, session, symbol: Symbol | None, file_row: File | None, targets: List[str]) -> float:
        if not targets:
            return 0.0

        cache = SymbolGraphCache.get_instance()
        cache.load(session=session)

        # Resolve target IDs from in-memory index
        target_ids = []
        for t in targets:
            sym = cache.get_symbol_by_qualified_name(t)
            if sym:
                target_ids.append(sym["id"])
            else:
                for sym in cache.get_symbols_by_name(t):
                    target_ids.append(sym["id"])

        if not target_ids:
            return 0.0

        # Check if the candidate symbol is within 1st degree neighborhood of target
        if symbol:
            for rel in cache.relationships_by_source.get(str(symbol.id), []):
                if rel["target_symbol_id"] in target_ids:
                    return 100.0
            for rel in cache.relationships_by_target.get(str(symbol.id), []):
                if rel["source_symbol_id"] in target_ids:
                    return 100.0

        # Check if the candidate file matches target file relationships
        if file_row:
            target_file_paths = set()
            for tid in target_ids:
                tsym = cache.get_symbol_by_id(tid)
                if tsym and tsym.get("file_path"):
                    target_file_paths.add(tsym["file_path"])

            file_id = cache.files_by_path.get(file_row.path)
            if file_id and target_file_paths:
                for rel in cache.relationships_by_file.get(file_id, []):
                    if rel["target_symbol_id"]:
                        tsym = cache.get_symbol_by_id(rel["target_symbol_id"])
                        if tsym and tsym.get("file_path") in target_file_paths:
                            return 100.0

        return 0.0

    def compute_test_score(self, session, symbol: Symbol | None, file_row: File | None, targets: List[str]) -> float:
        fpath = (file_row.path if file_row else "").lower()
        is_test_file = "test" in fpath or "spec" in fpath

        if not targets:
            return 50.0 if is_test_file else 0.0

        if file_row:
            try:
                cache = SymbolGraphCache.get_instance()
                cache.load(session=session)

                target_symbol_ids = []
                for t in targets:
                    sym = cache.get_symbol_by_qualified_name(t)
                    if sym:
                        target_symbol_ids.append(sym["id"])
                    else:
                        for sym in cache.get_symbols_by_name(t):
                            target_symbol_ids.append(sym["id"])

                if target_symbol_ids:
                    file_id = cache.files_by_path.get(file_row.path)
                    if file_id:
                        for test_rec in cache.tests_by_file.get(file_id, []):
                            if test_rec.get("target_symbol_id") in target_symbol_ids:
                                return 100.0

                        for sym_data in cache.symbols_by_id.values():
                            if sym_data.get("file_path") == file_row.path:
                                if sym_data["id"] in cache.tests_by_symbol:
                                    return 100.0
            except Exception as e:
                print(f"[HybridRanker] Test score computation exception: {e}")

        return 50.0 if is_test_file else 0.0

    def compute_lexical_score(self, query: str, chunk: Dict[str, Any]) -> float:
        """Calculate token-overlap/lexical matching score between query and candidate metadata."""
        query_words = set(re.findall(r"\b\w+\b", query.lower()))
        if not query_words:
            return 0.0
            
        symbol_name = (chunk.get("symbol") or chunk.get("name") or "").lower()
        file_path = (chunk.get("file") or "").lower()
        code_content = (chunk.get("code") or chunk.get("content") or "").lower()
        
        score = 0.0
        for word in query_words:
            if word in symbol_name:
                score += 50.0
            if word in file_path:
                score += 30.0
            if len(word) > 3 and word in code_content:
                score += 10.0
                
        return min(100.0, score)

    def compute_historical_score(self, file_path: str, committed_files: List[str]) -> float:
        if not file_path or not committed_files:
            return 0.0
        count = committed_files.count(file_path)
        if count > 0:
            return min(100.0, 50.0 + count * 10.0)
        return 0.0

