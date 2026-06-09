# context/context_ranker.py
#
# ContextRanker ranks candidate snippets based on proximity to target symbols,
# connection frequency, and semantic relevance scores.

from typing import List, Optional
from sqlalchemy import or_
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from context.context_package import Snippet
from editing.symbol_handle import SymbolHandle

class ContextRanker:
    def rank(
        self,
        snippets: List[Snippet],
        primary_symbol: Optional[SymbolHandle],
        callers: List[SymbolHandle] = None,
        callees: List[SymbolHandle] = None,
        related_tests: List[SymbolHandle] = None,
        session=None
    ) -> List[Snippet]:
        """
        Ranks snippets using proximity, connectivity, and semantic similarity.
        """
        if not snippets:
            return []

        db_sess = session
        close_session = False
        if db_sess is None and any(s.relevance == 0.0 for s in snippets):
            db_sess = SessionLocal()
            close_session = True

        caller_fqns = {c.fqn for c in callers} if callers else set()
        callee_fqns = {c.fqn for c in callees} if callees else set()
        test_fqns = {t.fqn for t in related_tests} if related_tests else set()

        ranked_snippets = []
        try:
            for snip in snippets:
                # 1. Distance Score
                if primary_symbol and (snip.symbol == primary_symbol.fqn or primary_symbol.fqn.split(".")[-1] in snip.symbol):
                    distance_score = 100.0
                elif snip.symbol in caller_fqns or snip.symbol in callee_fqns:
                    distance_score = 75.0
                elif snip.symbol in test_fqns or "Test" in snip.symbol:
                    distance_score = 60.0
                else:
                    distance_score = 30.0

                # 2. Connectivity Score (from DB relationships)
                connectivity_score = 0.0
                if db_sess:
                    # Look up symbol in DB
                    db_sym = db_sess.query(Symbol).filter(
                        or_(
                            Symbol.name == snip.symbol,
                            Symbol.qualified_name == snip.symbol
                        )
                    ).first()
                    if db_sym:
                        inbound = db_sess.query(SymbolRelationship).filter(
                            SymbolRelationship.target_symbol_id == db_sym.id
                        ).count()
                        outbound = db_sess.query(SymbolRelationship).filter(
                            SymbolRelationship.source_symbol_id == db_sym.id
                        ).count()
                        connectivity_score = min(20.0, (inbound + outbound) * 2.0)

                # 3. Base/Retrieval relevance weight
                retrieval_relevance = snip.relevance if snip.relevance > 0.0 else 0.5
                if retrieval_relevance > 1.0:
                    retrieval_relevance = retrieval_relevance / 100.0

                # Composite score calculation
                composite = distance_score * 0.60 + connectivity_score + (retrieval_relevance * 20.0)
                # Normalize composite score to range [0.0, 1.0]
                normalized_relevance = min(1.0, max(0.0, composite / 120.0))

                ranked_snippets.append(Snippet(
                    symbol=snip.symbol,
                    source=snip.source,
                    relevance=round(normalized_relevance, 3)
                ))

        except Exception as e:
            print(f"[ContextRanker] Warning: Snippet ranking failed: {e}")
            ranked_snippets = snippets
        finally:
            if close_session and db_sess:
                db_sess.close()

        # Sort descending by relevance score
        return sorted(ranked_snippets, key=lambda x: x.relevance, reverse=True)
