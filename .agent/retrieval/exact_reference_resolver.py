# .agent/retrieval/exact_reference_resolver.py
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class ResolvedReference:
    reference: str
    matches: List[str]
    status: str  # resolved, ambiguous, not_found


class ExactReferenceResolver:
    EXTENSIONS = (
        "py", "java", "ts", "tsx", "js", "jsx",
        "go", "rs", "cpp", "c", "h", "cs",
        "sql", "json", "yaml", "yml"
    )

    def __init__(self, repo_root: str, source_files: List[Path]):
        self.repo_root = Path(repo_root).resolve()
        self.files = [
            p.resolve() for p in source_files
        ]

    def resolve(self, query: str) -> List[ResolvedReference]:
        pattern = re.compile(
            r"(?<![\w./-])"
            r"([A-Za-z0-9_./-]+\.("
            + "|".join(self.EXTENSIONS) +
            r"))(?![\w./-])",
            re.IGNORECASE,
        )
        raw_matches = pattern.findall(query)
        references = [m[0] if isinstance(m, tuple) else m for m in raw_matches]
        resolved_refs: List[ResolvedReference] = []
        seen = set()

        for ref in references:
            normalized = ref.replace("\\", "/").lower()
            if normalized in seen:
                continue
            seen.add(normalized)

            is_path = "/" in normalized
            matches: List[str] = []

            for path in self.files:
                try:
                    rel = path.relative_to(self.repo_root)
                except ValueError:
                    rel = path
                rel_name = rel.as_posix().lower()

                if is_path:
                    matched = (
                        rel_name == normalized
                        or rel_name.endswith("/" + normalized)
                    )
                else:
                    matched = path.name.lower() == normalized

                if matched:
                    matches.append(rel.as_posix())

            if len(matches) == 1:
                status = "resolved"
            elif len(matches) > 1:
                status = "ambiguous"
            else:
                status = "not_found"

            resolved_refs.append(ResolvedReference(
                reference=ref,
                matches=matches,
                status=status,
            ))

        return resolved_refs
