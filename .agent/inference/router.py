# inference/router.py

import re
import time
import json
try:
    import requests
except ImportError:
    requests = None
import urllib.request
import urllib.error
from enum import Enum
from typing import Optional, List, Dict, Any

class TaskType(Enum):
    CHAT = "chat"
    RETRIEVAL = "retrieval"
    PLAN = "plan"
    EDIT_SMALL = "edit_small"
    EDIT_COMPLEX = "edit_complex"
    REFLECTION = "reflection"

class ModelRouter:
    # Class-level cache to share model lookup across instances and requests
    _cached_models: Optional[List[Dict[str, Any]]] = None
    _last_fetch_time: float = 0.0
    CACHE_TTL: float = 60.0  # seconds

    def __init__(self, host: str = "http://localhost:11434", default_model: str = "qwen2.5-coder:7b"):
        self.host = host.rstrip("/")
        self.default_model = default_model

    def _parse_size(self, model_info: Dict[str, Any]) -> Optional[float]:
        """
        Parses parameter size (in billions) from model info.
        Tries 'details.parameter_size' first, then falls back to regex on the name.
        """
        details = model_info.get("details") or {}
        param_size_str = details.get("parameter_size")
        
        if param_size_str and isinstance(param_size_str, str):
            # Parse strings like "1.5B", "7.6B", "32B"
            match = re.match(r"^([0-9.]+)[bB]?", param_size_str)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass

        # Fallback: parse from name, e.g. "qwen2.5-coder:7b" or "llama3.1:8b-instruct"
        name = model_info.get("name") or ""
        match = re.search(r"[:_-](\d+(?:\.\d+)?)[bB](?:[:_-]|$)", name)
        if not match:
            # Try a looser match anywhere in the name
            match = re.search(r"(\d+(?:\.\d+)?)[bB]", name)
            
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        return None

    def get_available_models(self) -> List[Dict[str, Any]]:
        """
        Fetches and parses available models from Ollama with caching.
        """
        now = time.time()
        if (
            ModelRouter._cached_models is not None
            and (now - ModelRouter._last_fetch_time) < ModelRouter.CACHE_TTL
        ):
            return ModelRouter._cached_models

        models = []
        try:
            if requests is not None:
                response = requests.get(f"{self.host}/api/tags", timeout=2.0)
                if response.status_code == 200:
                    data = response.json()
                else:
                    data = {}
            else:
                req = urllib.request.Request(f"{self.host}/api/tags")
                with urllib.request.urlopen(req, timeout=2.0) as res:
                    data = json.loads(res.read().decode("utf-8")) if res.status == 200 else {}
            models_raw = data.get("models") or []
            for m in models_raw:
                name = m.get("name") or ""
                # Filter out embedding or rerank models as they cannot handle chat
                if "embed" in name.lower() or "rerank" in name.lower():
                    continue
                
                size = self._parse_size(m)
                models.append({
                    "name": name,
                    "size": size
                })
        except Exception as e:
            # Silently catch/log server connection errors to prevent failure
            # We cache the empty list to avoid hammering the endpoint if down
            print(f"[ModelRouter] Warning: failed to fetch models from Ollama: {e}")

        ModelRouter._cached_models = models
        ModelRouter._last_fetch_time = now
        return models

    def route(self, task: TaskType) -> str:
        """
        Routes the task to the best matching pulled model name.
        """
        # Define ranges for each size tier
        # 1-3B: size < 5.0
        # 7-14B: 5.0 <= size < 20.0
        # 32B+: size >= 20.0
        tier_ranges = {
            "1-3B": (0.1, 5.0),
            "7-14B": (5.0, 20.0),
            "32B+": (20.0, 1000.0)
        }

        # Map TaskType to size tier
        task_tier_map = {
            TaskType.RETRIEVAL: "1-3B",
            TaskType.CHAT: "7-14B",
            TaskType.PLAN: "7-14B",
            TaskType.EDIT_SMALL: "7-14B",
            TaskType.EDIT_COMPLEX: "32B+",
            TaskType.REFLECTION: "7-14B"
        }

        target_tier = task_tier_map.get(task, "7-14B")
        min_size, max_size = tier_ranges[target_tier]

        models = self.get_available_models()
        candidates = []
        for m in models:
            size = m["size"]
            if size is not None and min_size <= size < max_size:
                candidates.append(m)

        if not candidates:
            # Fallback to default model if no model matches the tier
            return self.default_model

        # Sort candidates to prefer:
        # 1. coder models (contains 'coder')
        # 2. qwen models (contains 'qwen')
        # 3. alphabetically by name
        def sort_key(m):
            name_lower = m["name"].lower()
            is_coder = "coder" in name_lower
            is_qwen = "qwen" in name_lower
            # Since sorting is ascending, False (0) is sorted before True (1).
            # We want coder first, so we return 0 for coder, 1 for non-coder.
            return (0 if is_coder else 1, 0 if is_qwen else 1, name_lower)

        candidates.sort(key=sort_key)
        return candidates[0]["name"]
