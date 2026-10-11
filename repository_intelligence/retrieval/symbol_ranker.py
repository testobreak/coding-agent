from pathlib import Path
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.file import File


class SymbolRanker:
    """
    Symbol-First Multi-Signal Ranker (Phase 8).

    Scoring formula:
        score = (
            symbol_match   * 0.40   # exact / prefix name match
          + graph_distance * 0.25   # graph neighbourhood proximity
          + open_buffer    * 0.15   # same or nearby file as active file
          + semantic       * 0.15   # import / namespace signal
          + history        * 0.05   # relationship exists in graph
        )

    For explicit symbol queries symbol_match dominates.
    Semantic (embedding) score is a fallback, not the driver.
    """

    # Weights
    W_SYMBOL_MATCH   = 0.40
    W_GRAPH_DISTANCE = 0.25
    W_OPEN_BUFFER    = 0.15
    W_SEMANTIC       = 0.15
    W_HISTORY        = 0.05

    # Raw point constants (normalised to 0-1 before weighting)
    _EXACT_QUALIFIED = 1000.0
    _EXACT_NAME      = 200.0
    _PREFIX_NAME     = 40.0
    _NAMESPACE_MATCH = 50.0
    _IMPORT_MATCH    = 300.0
    _SAME_FILE       = 80.0
    _SAME_DIR        = 30.0
    _SAME_PARENT     = 20.0
    _GRAPH_DIRECT    = 100.0

    def rank(
        self,
        session,
        repository_id,
        target_name: str,
        candidates: list[Symbol],
        source_file: File | None = None,
        graph_distances: dict | None = None,
    ) -> list[Symbol]:
        """Rank candidate symbols using the symbol-first formula."""
        if not candidates:
            return []

        simple_target = target_name.split(".")[-1]

        # Pre-compute shared context once
        source_file_package = None
        imports: set = set()
        if source_file:
            source_file_package = self._get_file_package(session, source_file)
            import_rows = (
                session.query(SymbolRelationship.target_name)
                .filter(
                    SymbolRelationship.source_file_id == source_file.id,
                    SymbolRelationship.relationship_type == "USES",
                )
                .all()
            )
            imports = {r[0].strip() for r in import_rows if r[0]}

        scored = []
        for candidate in candidates:

            # ── 1. symbol_match ────────────────────────────────────────
            sym_raw = 0.0
            if candidate.qualified_name == target_name:
                sym_raw = self._EXACT_QUALIFIED
            elif candidate.name == simple_target:
                sym_raw = self._EXACT_NAME
            elif (
                candidate.name.startswith(simple_target)
                or simple_target.startswith(candidate.name)
            ):
                sym_raw = self._PREFIX_NAME
            sym_score = min(sym_raw / self._EXACT_QUALIFIED, 1.0)

            # ── 2. graph_distance ──────────────────────────────────────
            graph_raw = 0.0
            if graph_distances and candidate.id in graph_distances:
                dist = graph_distances[candidate.id]
                graph_raw = self._GRAPH_DIRECT / max(dist, 1)
            elif source_file:
                has_rel = session.query(SymbolRelationship).filter(
                    SymbolRelationship.repository_id == repository_id,
                    (
                        (SymbolRelationship.source_file_id == source_file.id)
                        & (SymbolRelationship.target_symbol_id == candidate.id)
                    )
                    | (
                        (SymbolRelationship.source_symbol_id == candidate.id)
                        & (SymbolRelationship.repository_id == repository_id)
                    ),
                ).first()
                if has_rel:
                    graph_raw = self._GRAPH_DIRECT
            graph_score = min(graph_raw / self._GRAPH_DIRECT, 1.0)

            # ── 3. open_buffer (file proximity) ───────────────────────
            buf_raw = 0.0
            if source_file and candidate.file_id:
                cand_file = (
                    session.query(File)
                    .filter(File.id == candidate.file_id)
                    .first()
                )
                if cand_file:
                    if cand_file.id == source_file.id:
                        buf_raw = self._SAME_FILE
                    else:
                        s_parts = Path(source_file.path).parts
                        c_parts = Path(cand_file.path).parts
                        common = sum(
                            1 for p1, p2 in zip(s_parts, c_parts) if p1 == p2
                        )
                        if common >= 3:
                            buf_raw += self._SAME_DIR
                        if Path(source_file.path).parent == Path(cand_file.path).parent:
                            buf_raw += self._SAME_PARENT
            buf_score = min(buf_raw / self._SAME_FILE, 1.0)

            # ── 4. semantic (import / namespace) ───────────────────────
            sem_raw = 0.0
            if candidate.qualified_name in imports or any(
                imp.endswith(f".{candidate.name}") for imp in imports
            ):
                sem_raw += self._IMPORT_MATCH
            if "." in target_name:
                target_ns = ".".join(target_name.split(".")[:-1])
                if target_ns and target_ns in (candidate.qualified_name or ""):
                    sem_raw += self._NAMESPACE_MATCH
            if source_file_package and source_file_package in (
                candidate.qualified_name or ""
            ):
                sem_raw += self._NAMESPACE_MATCH
            sem_score = min(sem_raw / self._IMPORT_MATCH, 1.0)

            # ── 5. history (any relationship exists) ───────────────────
            hist_score = 1.0 if graph_raw > 0 else 0.0

            # ── Weighted total ─────────────────────────────────────────
            total = (
                sym_score   * self.W_SYMBOL_MATCH
                + graph_score * self.W_GRAPH_DISTANCE
                + buf_score   * self.W_OPEN_BUFFER
                + sem_score   * self.W_SEMANTIC
                + hist_score  * self.W_HISTORY
            )
            scored.append((total, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored]

    def _get_file_package(self, session, source_file: File) -> str | None:
        """Infer the namespace/package of the given source file."""
        first_symbol = (
            session.query(Symbol)
            .filter(Symbol.file_id == source_file.id)
            .first()
        )
        if first_symbol and first_symbol.qualified_name:
            parts = first_symbol.qualified_name.split(".")
            if len(parts) > 1:
                return ".".join(parts[:-1])

        rel_path = getattr(source_file, "relative_path", None) or getattr(source_file, "path", None)
        if rel_path:
            normalized_path = rel_path.replace("\\", "/")
            parts = Path(normalized_path).with_suffix("").parts
            if len(parts) > 1:
                return ".".join(parts[:-1])

        return None
