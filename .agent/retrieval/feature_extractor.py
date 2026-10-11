# retrieval/feature_extractor.py
#
# Feature extractor for context-aware multi-signal ranking.

import os
import time
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class RetrievalContext:
    """
    IDE-aware Context for retrieval ranking.
    """
    active_file: Optional[str] = None
    open_tabs: List[str] = field(default_factory=list)
    active_symbol: Optional[str] = None
    recent_files: List[str] = field(default_factory=list)
    diagnostics: List[Any] = field(default_factory=list)
    cursor_line: Optional[int] = None

@dataclass
class RankingFeatures:
    """
    Explicit signals extracted for ranking candidate chunks.
    """
    embedding_score: float
    editor_score: float
    tab_score: float
    import_score: float
    symbol_score: float
    recency_score: float
    diagnostics_score: float

class FeatureExtractor:
    """
    Extracts features for candidates by mapping structural and IDE context signals.
    """
    @staticmethod
    def extract_features(
        chunk: Dict[str, Any],
        base_score: float,
        context: Optional[RetrievalContext] = None,
        db_session = None
    ) -> RankingFeatures:
        if not context:
            return RankingFeatures(
                embedding_score=base_score,
                editor_score=0.0,
                tab_score=0.0,
                import_score=0.0,
                symbol_score=0.0,
                recency_score=0.0,
                diagnostics_score=0.0
            )

        chunk_file = chunk.get("file") or chunk.get("file_path") or ""
        if chunk_file:
            chunk_file = os.path.normpath(chunk_file)

        active_file = context.active_file
        if active_file:
            active_file = os.path.normpath(active_file)

        # 1. Semantic similarity (base vector score)
        embedding_score = base_score

        # 2. Active editor proximity
        editor_score = 0.0
        if active_file and chunk_file == active_file:
            editor_score = 1.0
            # Line proximity boost if cursor is active
            if context.cursor_line is not None:
                start_line = chunk.get("start_line") or chunk.get("line") or 1
                line_diff = abs(start_line - context.cursor_line)
                editor_score += 0.5 * (1.0 / (1.0 + line_diff / 50.0))

        # 3. Open tabs boost
        tab_score = 0.0
        if context.open_tabs:
            normalized_tabs = [os.path.normpath(t) for t in context.open_tabs]
            if chunk_file in normalized_tabs:
                tab_score = 1.0

        # 4. Import graph proximity
        import_score = 0.0
        if active_file and chunk_file:
            imports = chunk.get("imports", [])
            for imp in imports:
                if chunk_file in imp or imp in chunk_file:
                    import_score = 1.0
                    break

        # 5. Symbol reference score
        symbol_score = 0.0
        chunk_symbol = chunk.get("symbol") or chunk.get("name") or ""
        active_symbol = context.active_symbol
        if active_symbol and chunk_symbol:
            if chunk_symbol == active_symbol:
                symbol_score = 1.0
            elif active_symbol in chunk_symbol or chunk_symbol in active_symbol:
                symbol_score = 0.8

        # 6. Recency score (edit history)
        recency_score = 0.0
        if chunk_file:
            if context.recent_files:
                normalized_recents = [os.path.normpath(r) for r in context.recent_files]
                if chunk_file in normalized_recents:
                    idx = normalized_recents.index(chunk_file)
                    recency_score = 1.0 / (1.0 + idx)

            if recency_score == 0.0:
                try:
                    if os.path.exists(chunk_file):
                        mtime = os.path.getmtime(chunk_file)
                        seconds_since_last_edit = time.time() - mtime
                        # decay weight using tau = 1800 (30 mins)
                        recency_score = math.exp(-min(seconds_since_last_edit, 86400) / 1800.0)
                except Exception:
                    pass

        # 7. Diagnostics score
        diagnostics_score = 0.0
        if context.diagnostics and chunk_file:
            for diag in context.diagnostics:
                diag_file = getattr(diag, "file", "") or (diag.get("file", "") if isinstance(diag, dict) else "")
                if diag_file and os.path.normpath(diag_file) == chunk_file:
                    diagnostics_score = 1.0
                    break

        return RankingFeatures(
            embedding_score=embedding_score,
            editor_score=editor_score,
            tab_score=tab_score,
            import_score=import_score,
            symbol_score=symbol_score,
            recency_score=recency_score,
            diagnostics_score=diagnostics_score
        )
