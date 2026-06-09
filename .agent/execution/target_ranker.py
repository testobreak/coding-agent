# execution/target_ranker.py
#
# Ranks modification target files by a multi-signal score:
#
#   1. Test failure source files (from FailureAnalysisEngine / failure_parser)
#      — highest weight: 10.0 per file
#   2. Retrieval score from semantic_retrieve results
#      — weight: FAISS cosine similarity (0–1)
#   3. Recently modified files (from state.modified_files)
#      — medium weight: 3.0 (recently touched = likely to need fixing again)
#   4. Recently retrieved symbols (from state.active_symbols / touched_files)
#      — low weight: 1.5
#
# Output: ordered list of (path, score) tuples, best first.
#

from typing import List, Tuple, Dict, Any


class TargetRanker:
    """
    Produces a ranked list of file paths that should be the next repair targets.

    Usage:
        ranker = TargetRanker()
        ranked = ranker.rank(state)
        top_targets = [path for path, score in ranked[:5]]
    """

    WEIGHT_FAILURE   = 10.0   # File appears in test failure stack trace
    WEIGHT_RETRIEVAL =  1.0   # Multiplied by retrieval cosine score (0-1)
    WEIGHT_MODIFIED  =  3.0   # File was recently modified by the agent
    WEIGHT_TOUCHED   =  1.5   # File was retrieved / touched earlier in task

    # =========================================================
    # MAIN
    # =========================================================

    def rank(self, state) -> List[Tuple[str, float]]:
        """
        Returns [(file_path, score), ...] sorted by score descending.
        `state` must be a TaskState (or any object with the relevant attrs).
        """
        scores: Dict[str, float] = {}

        def add(path: str, weight: float) -> None:
            if not path:
                return
            path = path.strip()
            scores[path] = scores.get(path, 0.0) + weight

        # -------------------------------------------------------
        # Signal 1: test failure source files (highest weight)
        # -------------------------------------------------------
        for path in getattr(state, "test_failure_targets", []):
            add(path, self.WEIGHT_FAILURE)

        # Also check structured test_failures list (populated by old path)
        for failure in getattr(state, "test_failures", []):
            if isinstance(failure, dict):
                for path in failure.get("likely_source_files", []):
                    add(path, self.WEIGHT_FAILURE)

        # -------------------------------------------------------
        # Signal 2: retrieval score from retrieved chunks
        # -------------------------------------------------------
        for chunk in getattr(state, "retrieved_chunks", []):
            path = chunk.get("file", "")
            score = float(chunk.get("score", 0.5))  # chunk may embed score
            add(path, self.WEIGHT_RETRIEVAL * score)

        # -------------------------------------------------------
        # Signal 3: recently modified files
        # -------------------------------------------------------
        modified = list(getattr(state, "modified_files", []) or [])
        # More recent = higher index in list, give extra weight to last 3
        for i, path in enumerate(modified):
            recency = 1.0 + (i / max(len(modified), 1)) * 0.5
            add(path, self.WEIGHT_MODIFIED * recency)

        # -------------------------------------------------------
        # Signal 4: touched / active files
        # -------------------------------------------------------
        for path in getattr(state, "touched_files", []):
            add(path, self.WEIGHT_TOUCHED)

        for symbol in getattr(state, "active_symbols", []):
            if isinstance(symbol, dict):
                path = symbol.get("file", "")
            else:
                path = str(symbol)
            add(path, self.WEIGHT_TOUCHED * 0.5)

        # -------------------------------------------------------
        # Normalise and sort
        # -------------------------------------------------------
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return ranked

    def top_targets(self, state, n: int = 5) -> List[str]:
        """Convenience: returns top N file paths."""
        return [path for path, _ in self.rank(state)[:n]]

    # =========================================================
    # LOOP DETECTION
    # =========================================================

    def detect_repeated_target(
        self,
        state,
        max_repeats: int = 3,
    ) -> List[str]:
        """
        Returns files that have been modified > max_repeats times in this task.
        These are stuck-repair candidates — the agent should stop and escalate.
        """
        modified = list(getattr(state, "modified_files", []) or [])
        counts: Dict[str, int] = {}
        for path in modified:
            counts[path] = counts.get(path, 0) + 1
        return [p for p, c in counts.items() if c > max_repeats]

    def detect_same_retrieval(
        self,
        state,
        window: int = 6,
    ) -> bool:
        """
        Returns True if the last `window` tool outputs all retrieved the
        same set of chunks — the classic retrieval loop.
        """
        history = getattr(state, "tool_outputs", [])[-window:]
        retrieve_outputs = [
            h for h in history
            if isinstance(h, dict) and h.get("tool") == "semantic_retrieve"
        ]
        if len(retrieve_outputs) < 3:
            return False
        # Compare chunk_id sets
        id_sets = [
            frozenset(
                item.get("chunk", {}).get("chunk_id", "")
                for item in (out.get("result") or [])
                if isinstance(item, dict)
            )
            for out in retrieve_outputs
        ]
        return len(set(id_sets)) == 1
