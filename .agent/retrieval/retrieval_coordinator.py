# .agent/retrieval/retrieval_coordinator.py
"""Retrieval Coordinator: Integrates candidate merging with AST evidence extraction."""
from pathlib import Path
from typing import List, Tuple, Optional

from retrieval.ast_evidence_selector import ASTEvidenceSelector, EvidenceSpan
from retrieval.tree_sitter_evidence_selector import TreeSitterEvidenceSelector
from retrieval.candidate_merger import MergeResult, FileCandidate


class RetrievalCoordinator:
    """
    Coordinates Step 1 + 2 (file candidate resolution and merging)
    with Step 3 (AST-aware source evidence extraction) across Python,
    Java, TypeScript, and TSX.
    """

    def __init__(
        self,
        agent,
        selector: Optional[ASTEvidenceSelector] = None,
        multi_lang_selector: Optional[TreeSitterEvidenceSelector] = None,
    ):
        self.agent = agent
        self.selector = selector or ASTEvidenceSelector()
        self.multi_lang_selector = multi_lang_selector or TreeSitterEvidenceSelector()
        self.unsupported_files: List[str] = []
        self.failed_extractions: List[Tuple[str, str]] = []

    def retrieve(
        self,
        query: str,
        max_candidates: int = 12,
        max_parse_files: Optional[int] = 5,
        max_spans_per_file: int = 3,
        max_lines_per_span: int = 25,
    ) -> Tuple[List[EvidenceSpan], MergeResult]:
        # Reset tracking per retrieval call
        self.unsupported_files = []
        self.failed_extractions = []

        # Step 1 + 2: Resolve and merge file candidates
        result = self.agent.retrieve_file_candidates(
            query,
            max_candidates=max_candidates,
        )
        evidence: List[EvidenceSpan] = []

        # Bounded selection policy: avoid parsing all candidates unnecessarily.
        # Mandatory candidates are always preserved; remaining slots filled from top optional candidates.
        candidates_to_parse = result.candidates
        if max_parse_files is not None and len(candidates_to_parse) > max_parse_files:
            mandatory = [c for c in candidates_to_parse if c.mandatory]
            optional = [c for c in candidates_to_parse if not c.mandatory]
            slots = max(0, max_parse_files - len(mandatory))
            candidates_to_parse = mandatory + optional[:slots]

        # Step 3: Extract code from selected files using language-aware dispatch
        for candidate in candidates_to_parse:
            relative_path = Path(candidate.file_path)
            path = Path(self.agent.repo_root) / relative_path

            if not path.is_file():
                self.failed_extractions.append((candidate.file_path, "File not found"))
                raise FileNotFoundError(path)

            suffix = path.suffix.lower()

            if suffix not in {".py", ".java", ".ts", ".tsx"}:
                self.unsupported_files.append(candidate.file_path)
                continue

            try:
                source = path.read_text(encoding="utf-8")
                if suffix == ".py":
                    spans = self.selector.select_python(
                        file_path=candidate.file_path,
                        source=source,
                        query=query,
                        max_spans=max_spans_per_file,
                        max_lines=max_lines_per_span,
                    )
                else:
                    spans = self.multi_lang_selector.select(
                        file_path=candidate.file_path,
                        source=source,
                        query=query,
                        max_spans=max_spans_per_file,
                        max_lines=max_lines_per_span,
                    )
                evidence.extend(spans)
            except Exception as e:
                self.failed_extractions.append((candidate.file_path, str(e)))

        return evidence, result
