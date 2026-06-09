from pathlib import Path
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from repository_intelligence.models.file import File


class SymbolResolver:
    """
    Context-aware resolver that maps target names (e.g. 'EmployeeService')
    to database Symbol entities using various strategies.
    Uses an Enterprise Multi-Stage candidate retrieval & ranking architecture.
    """

    def resolve(
        self,
        session,
        repository_id,
        target_name: str | None,
        source_file: File | None = None
    ) -> list[Symbol]:
        """
        Resolves a symbol name to a ranked list of candidate Symbol records.
        """
        if not target_name:
            return []

        # Clean target_name
        target_name = target_name.strip()

        candidates_dict = {}

        # 1. Exact Qualified Name Match
        eq_matches = (
            session.query(Symbol)
            .filter(
                Symbol.repository_id == repository_id,
                Symbol.qualified_name == target_name
            )
            .all()
        )
        for sym in eq_matches:
            candidates_dict[sym.id] = sym

        # 2. Context-Aware Import Matching (using USES relationships of the source file)
        if source_file:
            imports = (
                session.query(SymbolRelationship.target_name)
                .filter(
                    SymbolRelationship.source_file_id == source_file.id,
                    SymbolRelationship.relationship_type == "USES"
                )
                .all()
            )
            
            for (imported_path,) in imports:
                if imported_path:
                    clean_path = imported_path.strip()
                    if clean_path == target_name or clean_path.endswith(f".{target_name}"):
                        syms = (
                            session.query(Symbol)
                            .filter(
                                Symbol.repository_id == repository_id,
                                Symbol.qualified_name == clean_path
                            )
                            .all()
                        )
                        for sym in syms:
                            candidates_dict[sym.id] = sym

        # 3. Same-Package Resolution
        if source_file:
            package_ns = self._get_file_package(session, source_file)
            if package_ns:
                candidate_qualified_name = f"{package_ns}.{target_name}"
                syms = (
                    session.query(Symbol)
                    .filter(
                        Symbol.repository_id == repository_id,
                        Symbol.qualified_name == candidate_qualified_name
                    )
                    .all()
                )
                for sym in syms:
                    candidates_dict[sym.id] = sym

        # 4. Suffix / Fuzzy / Prefix Fallback Match
        simple_name = target_name.split(".")[-1]
        suffix_matches = (
            session.query(Symbol)
            .filter(
                Symbol.repository_id == repository_id,
                (
                    Symbol.qualified_name.endswith(f".{target_name}")
                    | (Symbol.name == simple_name)
                    | Symbol.name.startswith(simple_name)
                )
            )
            .all()
        )
        for sym in suffix_matches:
            candidates_dict[sym.id] = sym

        candidates = list(candidates_dict.values())

        # Rank candidates using our dedicated SymbolRanker
        from repository_intelligence.retrieval.symbol_ranker import SymbolRanker
        ranker = SymbolRanker()
        ranked_candidates = ranker.rank(
            session=session,
            repository_id=repository_id,
            target_name=target_name,
            candidates=candidates,
            source_file=source_file
        )

        return ranked_candidates

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
            # Normalize path delimiters for namespaces
            normalized_path = rel_path.replace("\\", "/")
            parts = Path(normalized_path).with_suffix("").parts
            if len(parts) > 1:
                return ".".join(parts[:-1])

        return None
