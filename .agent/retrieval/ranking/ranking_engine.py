import os
import sys
from datetime import datetime, timezone
from typing import List

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        ".."
    )
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.file import File
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from retrieval.ranking.score_models import RetrievalCandidate
from retrieval.ranking.scoring import calculate_final_score


class RankingEngine:
    """
    Ranks retrieval candidates using hybrid multi-signal scoring:
      - Embedding match score (semantic)
      - Graph score (symbol relationships)
      - File importance (centrality in codebase)
      - Recency (freshness of modification)
    """

    def rank(
        self,
        results: List[dict],
        session=None
    ) -> List[dict]:
        """
        Ranks a list of flat search results (each as {"score": float, "chunk": dict})
        and returns a sorted list of ranked results.
        """
        if not results:
            return []

        # 1. Convert search results to RetrievalCandidates
        candidates = []
        file_paths = set()
        symbol_qualified_names = set()

        for item in results:
            chunk = item.get("chunk", {})
            score = item.get("score", 0.0)

            # Map the FAISS/DB similarity score to embedding_score
            # Ensure it is bounded between 0.0 and 1.0
            emb_score = max(0.0, min(1.0, score))

            # Retrieve qualified symbol name or DB symbol ID if available
            symbol_id = chunk.get("symbol") or chunk.get("name")
            file_path = chunk.get("file")

            if file_path:
                file_paths.add(file_path)
            if symbol_id:
                symbol_qualified_names.add(symbol_id)

            candidates.append(
                RetrievalCandidate(
                    symbol_id=symbol_id,
                    embedding_score=emb_score,
                    chunk=chunk
                )
            )

        # 2. Batch retrieve Graph and File metadata from DB to avoid N+1 queries
        graph_stats = {}
        file_stats = {}

        if session is None:
            db_session = SessionLocal()
            close_session = True
        else:
            db_session = session
            close_session = False

        try:
            # A. Fetch relationship stats for matched symbols in batch
            if symbol_qualified_names:
                # Query symbols by qualified name in this repo context
                symbols = (
                    db_session.query(Symbol.id, Symbol.qualified_name)
                    .filter(Symbol.qualified_name.in_(list(symbol_qualified_names)))
                    .all()
                )
                symbol_ids = [s[0] for s in symbols]
                sym_id_to_qname = {s[0]: s[1] for s in symbols}

                if symbol_ids:
                    # Incoming connections count
                    incoming = (
                        db_session.query(SymbolRelationship.target_symbol_id, SymbolRelationship.id)
                        .filter(SymbolRelationship.target_symbol_id.in_(symbol_ids))
                        .all()
                    )
                    # Outgoing connections count
                    outgoing = (
                        db_session.query(SymbolRelationship.source_symbol_id, SymbolRelationship.id)
                        .filter(SymbolRelationship.source_symbol_id.in_(symbol_ids))
                        .all()
                    )

                    # Initialize stats
                    for qname in symbol_qualified_names:
                        graph_stats[qname] = 0

                    # Aggregate connection counts
                    for target_id, _ in incoming:
                        qname = sym_id_to_qname.get(target_id)
                        if qname:
                            graph_stats[qname] = graph_stats.get(qname, 0) + 1

                    for source_id, _ in outgoing:
                        qname = sym_id_to_qname.get(source_id)
                        if qname:
                            graph_stats[qname] = graph_stats.get(qname, 0) + 1

            # B. Fetch File stats (importance + recency) in batch
            if file_paths:
                files = (
                    db_session.query(File)
                    .filter(File.path.in_(list(file_paths)))
                    .all()
                )

                for f in files:
                    # symbols inside this file
                    symbol_count = (
                        db_session.query(Symbol.id)
                        .filter(Symbol.file_id == f.id)
                        .count()
                    )
                    # references targeting symbols in this file
                    references_count = (
                        db_session.query(SymbolRelationship.id)
                        .filter(SymbolRelationship.source_file_id == f.id)
                        .count()
                    )
                    
                    file_stats[f.path] = {
                        "updated_at": f.updated_at,
                        "importance_raw": symbol_count + references_count
                    }

        except Exception as e:
            # Soft fallback: if database access fails, print warning and proceed with default stats
            print(f"[RankingEngine] Warning: Metadata retrieval failed: {e}")
        finally:
            if close_session:
                db_session.close()

        # 3. Compute Normalized Sub-Scores for each Candidate
        max_graph_raw = max(graph_stats.values()) if graph_stats else 0
        max_file_raw = max(f["importance_raw"] for f in file_stats.values()) if file_stats else 0

        for candidate in candidates:
            chunk = candidate.chunk
            qname = candidate.symbol_id
            fpath = chunk.get("file")

            # Graph Score (Normalized)
            if qname and max_graph_raw > 0:
                raw_conn = graph_stats.get(qname, 0)
                candidate.graph_score = raw_conn / max_graph_raw
            else:
                candidate.graph_score = 0.0

            # File Importance & Recency (Normalized)
            if fpath and fpath in file_stats:
                stats = file_stats[fpath]
                # Importance
                if max_file_raw > 0:
                    candidate.file_importance_score = stats["importance_raw"] / max_file_raw
                else:
                    candidate.file_importance_score = 0.0
                
                # Recency
                candidate.recency_score = self._compute_recency_score(stats["updated_at"])
            else:
                candidate.file_importance_score = 0.0
                candidate.recency_score = 0.2

            # Compute composite final score
            calculate_final_score(candidate)

        # 4. Sort Candidates and Convert back to original dict list format
        sorted_candidates = sorted(
            candidates,
            key=lambda c: c.final_score,
            reverse=True
        )

        ranked_results = []
        for candidate in sorted_candidates:
            # Map back to matching results dict
            ranked_results.append({
                "score": candidate.final_score,
                "chunk": candidate.chunk
            })

        return ranked_results

    def _compute_recency_score(self, updated_at: datetime) -> float:
        """
        Calculates recency scoring based on modified elapsed days:
          - Modified today: 1.0
          - Modified this week: 0.8
          - Modified this month: 0.5
          - Old: 0.2
        """
        if not updated_at:
            return 0.2

        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = now - updated_at
        days = diff.days

        if days <= 0:
            return 1.0
        elif days <= 7:
            return 0.8
        elif days <= 30:
            return 0.5
        else:
            return 0.2
