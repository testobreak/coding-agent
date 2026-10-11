# repository_intelligence/manifest/query_engine.py

from typing import List, Dict, Any, Optional
from repository_intelligence.manifest.models import FileRecord, RepositoryManifest

class ManifestQueryEngine:
    @staticmethod
    def query(manifest: RepositoryManifest, filters: Dict[str, Any]) -> List[FileRecord]:
        """
        Query files matching specific criteria (language, module, file_type, path_contains).
        """
        candidates: List[FileRecord] = list(manifest.files_by_path.values())
        
        # Apply filters
        # 1. Module filter (leverage index if possible)
        module_filter = filters.get("module")
        if module_filter:
            if isinstance(module_filter, str):
                candidates = manifest.files_by_module.get(module_filter, [])
            elif isinstance(module_filter, (list, set, tuple)):
                candidates = []
                for m in module_filter:
                    candidates.extend(manifest.files_by_module.get(m, []))

        # 2. Language filter (leverage index if possible)
        lang_filter = filters.get("language")
        if lang_filter:
            # If candidates is empty (meaning no module index match), search full manifest, otherwise filter candidates
            source_pool = candidates if module_filter else list(manifest.files_by_path.values())
            if isinstance(lang_filter, str):
                candidates = [r for r in source_pool if r.language == lang_filter]
            elif isinstance(lang_filter, (list, set, tuple)):
                candidates = [r for r in source_pool if r.language in lang_filter]
                
        # 3. File type filter
        type_filter = filters.get("file_type")
        if type_filter:
            if isinstance(type_filter, str):
                candidates = [r for r in candidates if r.file_type == type_filter]
            elif isinstance(type_filter, (list, set, tuple)):
                candidates = [r for r in candidates if r.file_type in type_filter]

        # 4. Path substring match
        path_contains = filters.get("path_contains")
        if path_contains:
            pc = path_contains.lower()
            candidates = [r for r in candidates if pc in r.path.lower()]
            
        # 5. Has symbols filter
        has_symbols = filters.get("has_symbols")
        if has_symbols is not None:
            if has_symbols:
                candidates = [r for r in candidates if r.symbol_count > 0]
            else:
                candidates = [r for r in candidates if r.symbol_count == 0]
                
        # 6. Min size filter
        min_size = filters.get("min_size")
        if min_size is not None:
            candidates = [r for r in candidates if r.size_bytes >= min_size]

        # 7. Max size filter
        max_size = filters.get("max_size")
        if max_size is not None:
            candidates = [r for r in candidates if r.size_bytes <= max_size]

        return candidates
