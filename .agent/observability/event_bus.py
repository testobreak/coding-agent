# observability/event_bus.py

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, Optional

@dataclass
class CursorEvent:
    event_type: str
    request_id: str
    timestamp: float
    payload: Dict[str, Any]

class EventBus:
    _instance: Optional["EventBus"] = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

    def __init__(self, log_dir=None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        if log_dir is None:
            log_dir = Path(__file__).resolve().parent.parent / "logs"
        self.log_file = Path(log_dir) / "cursor_events.jsonl"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def emit(self, event_type: str, request_id: str, payload: Dict[str, Any]):
        event = CursorEvent(
            event_type=event_type,
            request_id=request_id,
            timestamp=time.time(),
            payload=payload
        )
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event)) + "\n")
        except Exception as e:
            print(f"[EventBus] Failed to emit event {event_type}: {e}")

    def clear(self):
        try:
            if self.log_file.exists():
                self.log_file.write_text("", encoding="utf-8")
        except Exception:
            pass
