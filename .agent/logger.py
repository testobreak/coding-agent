# logger.py

from pathlib import Path
from datetime import datetime


class Logger:

    def __init__(self, log_file=".agent/logs/agent.log"):

        self.log_path = Path(log_file)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message):

        timestamp = datetime.utcnow().isoformat()

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
