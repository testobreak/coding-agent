# execution/evidence_store.py
#
# VerificationEvidenceStore logs and persists verification run history to disk.

import json
import os
from datetime import datetime
from typing import List, Dict, Any
from execution.verification_result import VerificationResult

class VerificationEvidenceStore:
    def __init__(self, history_path: str = "logs/verification_history.json"):
        self.history_path = history_path

    def log_run(self, result: VerificationResult, plan_id: str = "unknown") -> Dict[str, Any]:
        """
        Logs a verification result run and persists it to disk.
        """
        # Ensure directories exist
        os.makedirs(os.path.dirname(self.history_path) if os.path.dirname(self.history_path) else ".", exist_ok=True)
        
        run_data = {
            "timestamp": datetime.now().isoformat(),
            "plan_id": plan_id,
            "status": result.status.value,
            "build_success": result.build_passed,
            "tests_success": result.tests_passed,
            "lint_success": result.lint_passed,
            "issues_count": len(result.issues),
            "issues": [
                {
                    "type": i.type,
                    "file": i.file,
                    "line": i.line,
                    "message": i.message,
                    "severity": i.severity,
                    "category": i.category
                }
                for i in result.issues
            ],
            "evidence": [
                {
                    "name": ev.name,
                    "content": ev.content,
                    "timestamp": ev.timestamp
                }
                for ev in result.evidence
            ]
        }
        
        # Load existing history
        history = self.load_history()
        history.append(run_data)
        
        # Keep history capped at 100 entries to prevent file bloating
        if len(history) > 100:
            history = history[-100:]
            
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
            
        return run_data

    def load_history(self) -> List[Dict[str, Any]]:
        """
        Loads verification runs history from disk.
        """
        if not os.path.exists(self.history_path):
            return []
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[VerificationEvidenceStore] Warning: Failed to load history: {e}")
            return []
