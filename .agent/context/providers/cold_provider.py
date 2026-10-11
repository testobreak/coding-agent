# context/providers/cold_provider.py
from typing import Any

class ColdProvider:
    def __init__(self, state: Any):
        self.state = state

    def resolve(self) -> dict:
        failed_steps = getattr(self.state.episodic_memory, "failed_attempts", []) if getattr(self.state, "episodic_memory", None) else []
        reflections = getattr(self.state.episodic_memory, "reflections", []) if getattr(self.state, "episodic_memory", None) else []
        summaries = getattr(self.state.episodic_memory, "summaries", []) if getattr(self.state, "episodic_memory", None) else []
        tool_outputs = getattr(self.state.archive_memory, "tool_outputs", []) if getattr(self.state, "archive_memory", None) else []
        raw_logs = getattr(self.state.archive_memory, "raw_logs", []) if getattr(self.state, "archive_memory", None) else []
        
        runtime_memory = {}
        if getattr(self.state, "runtime_memory", None):
            runtime_memory = {
                "iterations": getattr(self.state.runtime_memory, "total_iterations", 0),
                "tool_calls": getattr(self.state.runtime_memory, "tool_call_count", 0),
                "retrievals": getattr(self.state.runtime_memory, "retrieval_count", 0),
                "repairs": getattr(self.state.runtime_memory, "repair_count", 0),
                "runtime_errors": getattr(self.state.runtime_memory, "runtime_errors", [])
            }
            
        return {
            "failed_steps": failed_steps,
            "reflections": reflections,
            "summaries": summaries,
            "recent_tool_outputs": tool_outputs,
            "execution_history": raw_logs,
            "runtime_memory": runtime_memory,
            "architecture_notes": getattr(self.state, "architecture_notes", [])
        }
