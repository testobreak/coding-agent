# context/cache.py
#
# Context Cache for caching assembled prompts, tokenized prompts, and symbol context.
# Keyed by: (task_id, active_file, touched_files_hash)

import os
import hashlib
import subprocess
from typing import Dict, Tuple, Any, Optional
from dataclasses import dataclass

@dataclass
class CachedContext:
    assembled_prompt: Any
    tokenized_prompt: Any
    symbol_context: Any

class ContextCache:
    # Class-level dictionary for cache storage
    # Key: (task_id, active_file, touched_files_hash)
    # Value: CachedContext
    _cache: Dict[Tuple[Optional[str], Optional[str], str], CachedContext] = {}

    @classmethod
    def get_touched_files_hash(cls, repo_root: Optional[str], active_file: Optional[str]) -> str:
        """
        Computes a sha256 hash representing the current "modification state" of the project.
        This incorporates:
        1. The active file's modification time (mtime).
        2. Git status --porcelain output to capture other touched files in the repo.
        """
        if not repo_root:
            repo_root = os.getcwd()
            
        hasher = hashlib.sha256()
        
        # 1. Incorporate active file mtime and name
        if active_file:
            hasher.update(active_file.encode('utf-8'))
            abs_active = active_file
            if not os.path.isabs(abs_active):
                abs_active = os.path.join(repo_root, active_file)
            if os.path.exists(abs_active):
                try:
                    mtime = os.path.getmtime(abs_active)
                    hasher.update(str(mtime).encode('utf-8'))
                except Exception:
                    pass
        
        # 2. Incorporate git status changes to reflect modifications in other files
        if os.path.exists(os.path.join(repo_root, ".git")):
            try:
                res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=2
                )
                if res.returncode == 0 and res.stdout:
                    hasher.update(res.stdout.encode('utf-8'))
            except Exception:
                pass
                
        return hasher.hexdigest()

    @classmethod
    def get(cls, task_id: Optional[str], active_file: Optional[str], repo_root: Optional[str] = None) -> Optional[CachedContext]:
        """
        Retrieves a cached context from the Cache.
        """
        if not repo_root:
            repo_root = os.getcwd()
        hash_val = cls.get_touched_files_hash(repo_root, active_file)
        key = (task_id, active_file, hash_val)
        if key in cls._cache:
            return cls._cache[key]
            
        # Fallback: search for any entry matching active_file and hash_val
        for cache_key, val in cls._cache.items():
            _, act_file, h_val = cache_key
            if act_file == active_file and h_val == hash_val:
                return val
                
        return None

    @classmethod
    def set(
        cls,
        task_id: Optional[str],
        active_file: Optional[str],
        repo_root: Optional[str],
        assembled_prompt: Any,
        tokenized_prompt: Any,
        symbol_context: Any
    ) -> None:
        """
        Inserts/updates the cache with the given context components.
        """
        if not repo_root:
            repo_root = os.getcwd()
        hash_val = cls.get_touched_files_hash(repo_root, active_file)
        key = (task_id, active_file, hash_val)
        cls._cache[key] = CachedContext(
            assembled_prompt=assembled_prompt,
            tokenized_prompt=tokenized_prompt,
            symbol_context=symbol_context
        )

    @classmethod
    def clear(cls) -> None:
        """
        Clears all cached contexts.
        """
        cls._cache.clear()
