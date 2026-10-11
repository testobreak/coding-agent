# context/relevance_ranker.py

from typing import List, Any, Optional

class RelevanceRanker:
    @staticmethod
    def score_item(
        item: Any,
        request: str,
        primary_symbol_fqn: Optional[str] = None,
        diagnostics: Optional[List[Any]] = None,
        index: int = 0,
        total_items: int = 1
    ) -> float:
        """
        Calculates a competitive relevance score for a context item based on:
        score = semantic_similarity * 0.35 + symbol_overlap * 0.30 + recency * 0.15 + diagnostics_relevance * 0.20
        """
        # Convert item to a string representation for analysis
        item_text = ""
        if isinstance(item, dict):
            item_text = " ".join(str(v) for v in item.values())
        else:
            item_text = str(item)
            
        request_lower = (request or "").lower()
        item_lower = item_text.lower()
        
        # 1. Semantic Similarity (Word overlap)
        semantic_similarity = 0.0
        req_words = set(request_lower.split())
        if req_words:
            item_words = set(item_lower.split())
            semantic_similarity = len(req_words.intersection(item_words)) / len(req_words)
            
        # 2. Symbol Overlap
        symbol_overlap = 0.0
        if primary_symbol_fqn:
            parts = primary_symbol_fqn.lower().split(".")
            matches = sum(1 for p in parts if p and p in item_lower)
            symbol_overlap = matches / len(parts)
            
        # 3. Recency (higher index in history list is more recent)
        recency = 1.0
        if total_items > 1:
            recency = float(index) / (total_items - 1)
            
        # 4. Diagnostics Relevance
        diagnostics_relevance = 0.0
        if diagnostics:
            diag_str = " ".join(str(d).lower() for d in diagnostics)
            diag_words = set(diag_str.split())
            if diag_words:
                item_words = set(item_lower.split())
                diagnostics_relevance = len(diag_words.intersection(item_words)) / max(1, len(diag_words))
            if "error" in item_lower or "fail" in item_lower or "exception" in item_lower:
                diagnostics_relevance = max(diagnostics_relevance, 0.5)
                
        # Calculate composite score
        score = (
            semantic_similarity * 0.35 +
            symbol_overlap * 0.30 +
            recency * 0.15 +
            diagnostics_relevance * 0.20
        )
        return round(score, 4)

    @staticmethod
    def rank_and_budget(
        items: List[Any],
        request: str,
        primary_symbol_fqn: Optional[str] = None,
        diagnostics: Optional[List[Any]] = None,
        token_limit: int = 1000
    ) -> List[Any]:
        """
        Ranks all items by relevance score, then yields items until the hard token limit is hit.
        1 token is approximated as 4 characters.
        """
        if not items:
            return []
            
        scored_items = []
        n = len(items)
        for idx, item in enumerate(items):
            score = RelevanceRanker.score_item(
                item=item,
                request=request,
                primary_symbol_fqn=primary_symbol_fqn,
                diagnostics=diagnostics,
                index=idx,
                total_items=n
            )
            scored_items.append((score, item))
            
        # Sort items descending by score
        scored_items.sort(key=lambda x: x[0], reverse=True)
        
        selected = []
        total_tokens = 0
        for score, item in scored_items:
            item_char_len = len(str(item))
            item_tokens = max(1, item_char_len // 4)
            if total_tokens + item_tokens <= token_limit:
                selected.append(item)
                total_tokens += item_tokens
            else:
                # If budget is full, stop adding
                if token_limit > 0 and len(selected) > 0:
                    continue
                elif token_limit > 0:
                    # Always include at least one item if list is non-empty and limit is non-zero
                    selected.append(item)
                    break
        return selected
