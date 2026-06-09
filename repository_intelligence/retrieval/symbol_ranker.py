from pathlib import Path
from sqlalchemy import text
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.file import File


class SymbolRanker:
    """
    Enterprise Multi-Stage Symbol Ranker.
    Ranks resolved symbol candidates using a multi-signal scoring formula:
    total_score = (
          exact_match_score
        + namespace_score
        + graph_score
        + file_proximity_score
        + import_score
        + embedding_score
    )
    """

    def rank(
        self,
        session,
        repository_id,
        target_name: str,
        candidates: list[Symbol],
        source_file: File | None = None
    ) -> list[Symbol]:
        """
        Ranks a list of candidate symbols based on structural context and scoring rules.
        """
        if not candidates:
            return []

        # Infer source file namespace/package if source_file is provided
        source_file_package = None
        if source_file:
            source_file_package = self._get_file_package(session, source_file)

        # Pre-query all imports of the source file to make import matching fast
        imports = set()
        if source_file:
            import_rows = (
                session.query(SymbolRelationship.target_name)
                .filter(
                    SymbolRelationship.source_file_id == source_file.id,
                    SymbolRelationship.relationship_type == "USES"
                )
                .all()
            )
            imports = {r[0].strip() for r in import_rows if r[0]}

        ranked = []

        for candidate in candidates:
            score = 0.0

            # 1. Exact Qualified Name Match (Phase 3)
            if candidate.qualified_name == target_name:
                score += 1000.0

            # 2. Exact Symbol Name Match (Phase 4)
            simple_target = target_name.split(".")[-1]
            if candidate.name == simple_target:
                score += 200.0

            # 3. Prefix Match (Phase 5)
            elif candidate.name.startswith(simple_target) or simple_target.startswith(candidate.name):
                score += 40.0

            # 4. Namespace Weighting (Phase 2)
            if "." in target_name:
                target_ns = ".".join(target_name.split(".")[:-1])
                if target_ns and target_ns in candidate.qualified_name:
                    score += 50.0

            # Also give namespace boost if candidate shares same package namespace as source file
            if source_file_package and source_file_package in candidate.qualified_name:
                score += 50.0

            # 5. Import Score
            if candidate.qualified_name in imports or any(imp.endswith(f".{candidate.name}") for imp in imports):
                score += 300.0

            # 6. Import Graph Weighting (Phase 6)
            if source_file:
                has_rel = session.query(SymbolRelationship).filter(
                    SymbolRelationship.repository_id == repository_id,
                    (
                        (SymbolRelationship.source_file_id == source_file.id) &
                        (SymbolRelationship.target_symbol_id == candidate.id)
                    ) |
                    (
                        (SymbolRelationship.source_symbol_id == candidate.id) &
                        (SymbolRelationship.repository_id == repository_id)
                    )
                ).first()
                if has_rel:
                    score += 150.0

            # 7. File Proximity Score (Phase 7)
            if source_file and candidate.file_id:
                candidate_file = session.query(File).filter(File.id == candidate.file_id).first()
                if candidate_file:
                    if candidate_file.id == source_file.id:
                        score += 80.0
                    else:
                        source_parts = Path(source_file.path).parts
                        candidate_parts = Path(candidate_file.path).parts
                        common_prefix_count = 0
                        for p1, p2 in zip(source_parts, candidate_parts):
                            if p1 == p2:
                                common_prefix_count += 1
                            else:
                                break
                        if common_prefix_count >= 3:
                            score += 30.0
                        if Path(source_file.path).parent == Path(candidate_file.path).parent:
                            score += 20.0

            ranked.append((score, candidate))

        # Sort candidate list descending by score
        ranked.sort(key=lambda x: x[0], reverse=True)

        # Print debug logging for scoring transitions (pure ASCII only to prevent Windows console encoding crashes)
        for sc, cand in ranked[:5]:
            print(f"[SymbolRanker] Scored Candidate {cand.qualified_name}: Score {sc:.1f}")

        return [item[1] for item in ranked]

    def _get_file_package(self, session, source_file: File) -> str | None:
        """
        Infers the namespace/package of the given source file.
        """
        # A: Check first symbol's qualified name in this file
        first_symbol = (
            session.query(Symbol)
            .filter(Symbol.file_id == source_file.id)
            .first()
        )
        if first_symbol and first_symbol.qualified_name:
            parts = first_symbol.qualified_name.split(".")
            if len(parts) > 1:
                return ".".join(parts[:-1])

        # B: Fallback to parsing package/namespace from relative path
        rel_path = getattr(source_file, "relative_path", None) or getattr(source_file, "path", None)
        if rel_path:
            normalized_path = rel_path.replace("\\", "/")
            parts = Path(normalized_path).with_suffix("").parts
            if len(parts) > 1:
                return ".".join(parts[:-1])

        return None
