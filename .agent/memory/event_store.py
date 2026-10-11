# memory/event_store.py
import json
import time
from pathlib import Path

class EventStore:
    def __init__(self, root_dir=None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent / "events"
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def append_event(self, task_id: str, event: dict):
        """Append an event to the task's JSONL log file."""
        if not task_id:
            return
        path = self.root_dir / f"{task_id}_events.jsonl"
        if "timestamp" not in event:
            event["timestamp"] = time.time()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def query_events(self, task_id: str) -> list:
        """Query all events for a given task ID."""
        if not task_id:
            return []
        path = self.root_dir / f"{task_id}_events.jsonl"
        if not path.exists():
            return []
        events = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line.strip()))
        return events
