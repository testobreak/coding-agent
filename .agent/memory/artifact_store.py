# memory/artifact_store.py
import json
from pathlib import Path

class ArtifactStore:
    def __init__(self, root_dir=None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent / "artifacts"
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _task_dir(self, task_id: str) -> Path:
        d = self.root_dir / task_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_artifact(self, task_id: str, name: str, content: str) -> str:
        """Write content to an artifact file and return its relative path."""
        path = self._task_dir(task_id) / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def write_json_artifact(self, task_id: str, name: str, data: dict) -> str:
        """Write data to a JSON artifact file and return its relative path."""
        path = self._task_dir(task_id) / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(path)
