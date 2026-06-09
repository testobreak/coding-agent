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
        
        self.final_score = 0.0


class HybridRanker:
    """
    Next-Level Enterprise Multi-Signal Retrieval Ranker.
    """
    def __init__(self):
        # Specific weights requested by the user
        self.symbol_weight = 0.35
        self.graph_weight = 0.20
        self.embedding_weight = 0.15
        self.path_weight = 0.10
        self.impact_weight = 0.10
        self.test_weight = 0.05
        self.historical_weight = 0.05

    def extract_target_symbols(self, query: str) -> List[str]:
        """
        Zero-latency heuristic extractor capturing camel-cased symbol tokens
        or dotted namespaces from the query.
        """
        # CamelCase tokens (e.g. EmployeeService, EmployeeController)
        camel_case = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', query)
        # Dotted namespace paths (e.g. com.hrms.EmployeeService)
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

            for item in candidates:
                cand = RetrievalCandidate(item)
                chunk = cand.chunk

                fpath = chunk.get("file")
                file_row = db_files.get(fpath) if fpath else None

                sname = chunk.get("symbol") or chunk.get("name")
                symbol_row = db_symbols.get(sname) if sname else None

                # Calculate 7 distinct signals (each normalized to 0 - 100 range)
                
                # Signal 1: Embedding score
                cand.embedding_score = self.compute_embedding_score(item)

                # Signal 2: Symbol exact/partial match
                cand.symbol_score = self.compute_symbol_score(targets, chunk, symbol_row)

                # Signal 3: Graph centrality & direct connections
                cand.graph_score = self.compute_graph_score(db_session, symbol_row, targets)

                # Signal 4: Path segment match
                cand.path_score = self.compute_path_score(query, fpath)

                # Signal 5: Impact boundary neighbors
                cand.impact_score = self.compute_impact_score(db_session, symbol_row, file_row, targets)

                # Signal 6: Test relationships
                cand.test_score = self.compute_test_score(db_session, symbol_row, file_row, targets)

                # Signal 7: Historical success modifications
                cand.historical_score = 100.0 if fpath in committed_files else 0.0

                # Compute exact composite score
                cand.final_score = (
                    cand.symbol_score     * self.symbol_weight
                    + cand.graph_score      * self.graph_weight
                    + cand.embedding_score  * self.embedding_weight
                    + cand.path_score       * self.path_weight
                    + cand.impact_score     * self.impact_weight
                    + cand.test_score       * self.test_weight
                    + cand.historical_score * self.historical_weight
                )

                # Save metrics in chunk for transparency and logging
                chunk["_ranking_diagnostics"] = {
                    "symbol": cand.symbol_score,
                    "graph": cand.graph_score,
                    "embedding": cand.embedding_score,
                    "path": cand.path_score,
                    "impact": cand.impact_score,
                    "test": cand.test_score,
                    "historical": cand.historical_score
                }

                item["score"] = cand.final_score
                ranked_items.append(item)

        except Exception as e:
            print(f"[HybridRanker] Enterprise ranking encountered error: {e}")
            # Soft fallback
            return sorted(candidates, key=lambda x: x.get("score", 0.0), reverse=True)
        finally:
            if close_session:
                db_session.close()

        # Sort descending by composite score
        return sorted(ranked_items, key=lambda x: x.get("score", 0.0), reverse=True)

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

        # First pass: Check all targets for exact match
        for target in targets:
            target_lower = target.lower()
            if chunk_name == target_lower or chunk_symbol == target_lower:
                return 100.0
            if symbol and (symbol.qualified_name.lower() == target_lower or symbol.name.lower() == target_lower):
                return 100.0
            
        # Second pass: Check all targets for partial match
        for target in targets:
            target_lower = target.lower()
            if target_lower in chunk_name or target_lower in chunk_symbol:
                return 50.0
            if symbol and (target_lower in symbol.qualified_name.lower() or target_lower in symbol.name.lower()):
                return 50.0

        return 0.0

    def compute_graph_score(self, session, symbol: Symbol | None, targets: List[str]) -> float:
        if not symbol or not targets:
            return 0.0

        # Check for direct relationship (1st-degree hop) in DB targeting query symbols
        target_rows = session.query(Symbol.id).filter(
            Symbol.qualified_name.in_(targets) | Symbol.name.in_(targets)
        ).all()
        target_ids = [r[0] for r in target_rows]

        if target_ids:
            edge = session.query(SymbolRelationship.id).filter(
                SymbolRelationship.repository_id == symbol.repository_id,
                (
                    (SymbolRelationship.source_symbol_id == symbol.id) & 
                    (SymbolRelationship.target_symbol_id.in_(target_ids))
                ) |
                (
                    (SymbolRelationship.source_symbol_id.in_(target_ids)) & 
                    (SymbolRelationship.target_symbol_id == symbol.id)
                )
            ).first()
            if edge:
                return 100.0

        # Fallback to normalized centrality density
        inbound = session.query(SymbolRelationship.id).filter(SymbolRelationship.target_symbol_id == symbol.id).count()
        outbound = session.query(SymbolRelationship.id).filter(SymbolRelationship.source_symbol_id == symbol.id).count()
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

        target_rows = session.query(Symbol.id).filter(
            Symbol.qualified_name.in_(targets) | Symbol.name.in_(targets)
        ).all()
        target_ids = [r[0] for r in target_rows]

        if not target_ids:
            return 0.0

        # Check if the candidate symbol is within 1st degree neighborhood of target
        if symbol:
            related = session.query(SymbolRelationship.id).filter(
                (SymbolRelationship.source_symbol_id == symbol.id) & (SymbolRelationship.target_symbol_id.in_(target_ids)) |
                (SymbolRelationship.source_symbol_id.in_(target_ids)) & (SymbolRelationship.target_symbol_id == symbol.id)
            ).first()
            if related:
                return 100.0

        # Check if the candidate file matches target file relationships
        if file_row:
            target_files = session.query(Symbol.file_id).filter(Symbol.id.in_(target_ids)).all()
            target_file_ids = [r[0] for r in target_files if r[0]]
            if target_file_ids:
                # Direct relationships from candidate's file to target files (outbound)
                related_out = session.query(SymbolRelationship.id).join(
                    Symbol, SymbolRelationship.target_symbol_id == Symbol.id
                ).filter(
                    SymbolRelationship.source_file_id == file_row.id,
                    Symbol.file_id.in_(target_file_ids)
                ).first()
                if related_out:
                    return 100.0

                # Direct relationships from target files to candidate's file (inbound)
                related_in = session.query(SymbolRelationship.id).join(
                    Symbol, SymbolRelationship.target_symbol_id == Symbol.id
                ).filter(
                    SymbolRelationship.source_file_id.in_(target_file_ids),
                    Symbol.file_id == file_row.id
                ).first()
                if related_in:
                    return 100.0

        return 0.0

    def compute_test_score(self, session, symbol: Symbol | None, file_row: File | None, targets: List[str]) -> float:
        # Check if file path represents a test class
        fpath = (file_row.path if file_row else "").lower()
        is_test_file = "test" in fpath or "spec" in fpath

        if not targets:
            return 50.0 if is_test_file else 0.0

        if file_row:
            try:
                # 1. Check if the candidate file is a test for one of our target symbols
                target_symbol_ids = session.query(Symbol.id).filter(
                    Symbol.qualified_name.in_(targets) | Symbol.name.in_(targets)
                ).all()
                target_symbol_ids = [r[0] for r in target_symbol_ids]

                if target_symbol_ids:
                    test_for_target = session.query(DBTest.id).filter(
                        DBTest.file_id == file_row.id,
                        DBTest.target_symbol_id.in_(target_symbol_ids)
                    ).first()
                    if test_for_target:
                        return 100.0

                # 2. Check if there is any test pointing to a symbol in this candidate file
                candidate_symbol_ids = session.query(Symbol.id).filter(
                    Symbol.file_id == file_row.id
                ).all()
                candidate_symbol_ids = [r[0] for r in candidate_symbol_ids]

                if candidate_symbol_ids:
                    has_test = session.query(DBTest.id).filter(
                        DBTest.target_symbol_id.in_(candidate_symbol_ids)
                    ).first()
                    if has_test:
                        return 100.0
            except Exception as e:
                print(f"[HybridRanker] Test score computation exception: {e}")

        return 50.0 if is_test_file else 0.0

