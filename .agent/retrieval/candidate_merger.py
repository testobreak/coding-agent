"""Merge mandatory exact-file references with lexical candidates."""
from dataclasses import dataclass
from typing import List, Optional, Any


@dataclass(frozen=True)
class FileCandidate:
    file_path: str
    score: float
    mandatory: bool = False
    reason: str = "lexical"


@dataclass
class MergeResult:
    candidates: List[FileCandidate]
    missing: List[str]
    ambiguous: List[str]


class CandidateMerger:
    def merge(
        self,
        exact_references: List[Any],
        lexical_snippets: List[Any],
        max_candidates: int = 12,
    ) -> MergeResult:
        mandatory = {}
        missing = []
        ambiguous = []

        for ref in exact_references:
            if ref.status == "not_found":
                missing.append(ref.reference)
            elif ref.status == "ambiguous":
                ambiguous.append(ref.reference)
            elif ref.status == "resolved":
                for match in ref.matches:
                    mandatory[match] = FileCandidate(
                        file_path=match,
                        score=100.0,
                        mandatory=True,
                        reason=f"explicit_reference: {ref.reference}",
                    )

        lexical_by_file = {}
        for s in lexical_snippets:
            fp = s.file_path
            sc = s.relevance_score
            if fp not in lexical_by_file or sc > lexical_by_file[fp]:
                lexical_by_file[fp] = sc

        for fp, cand in list(mandatory.items()):
            if fp in lexical_by_file:
                boosted_score = lexical_by_file[fp] + 100.0
                mandatory[fp] = FileCandidate(
                    file_path=fp,
                    score=boosted_score,
                    mandatory=True,
                    reason=f"{cand.reason} + lexical",
                )

        mandatory_candidates = sorted(
            mandatory.values(),
            key=lambda c: c.score,
            reverse=True,
        )

        if len(mandatory_candidates) > max_candidates:
            raise ValueError(
                f"Mandatory candidates ({len(mandatory_candidates)}) "
                f"exceed max_candidates ({max_candidates})"
            )

        remaining_slots = max_candidates - len(mandatory_candidates)

        optional_candidates = [
            FileCandidate(
                file_path=fp,
                score=sc,
                mandatory=False,
                reason="lexical",
            )
            for fp, sc in lexical_by_file.items()
            if fp not in mandatory
        ]
        optional_candidates.sort(key=lambda c: c.score, reverse=True)

        selected = (
            mandatory_candidates
            + optional_candidates[:remaining_slots]
        )

        return MergeResult(
            candidates=selected,
            missing=missing,
            ambiguous=ambiguous,
        )
