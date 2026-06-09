from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class PromptContext:
    """
    Enterprise-grade, strongly-typed representation of the agent execution context.
    Provides complete type safety and structural validation.
    """
    goal: str = ""
    status: str = ""
    current_step: str = ""
    pending_executions: List[Any] = field(default_factory=list)
    current_plan: List[Any] = field(default_factory=list)
    failed_steps: List[Any] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    test_failures: List[Any] = field(default_factory=list)
    repair_history: List[Any] = field(default_factory=list)
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    active_symbols: List[str] = field(default_factory=list)
    touched_files: List[str] = field(default_factory=list)
    modification_targets: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    generated_code: List[str] = field(default_factory=list)
    reflections: List[Any] = field(default_factory=list)
    architecture_notes: List[str] = field(default_factory=list)
    recent_tool_outputs: List[Any] = field(default_factory=list)
    execution_history: List[Any] = field(default_factory=list)
    runtime_memory: Dict[str, Any] = field(default_factory=dict)
    loop_warning: bool = False
    callers: List[Dict[str, Any]] = field(default_factory=list)
    callees: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptContext":
        """
        Safely construct a PromptContext dataclass from a raw dictionary.
        Supports seamless backward compatibility.
        """
        if not data:
            return cls()
        
        # Get all defined dataclass field names
        fields = cls.__dataclass_fields__.keys()
        
        # Populate matching attributes, ignoring unexpected keys
        filtered = {}
        for f in fields:
            if f in data:
                filtered[f] = data[f]
                
        return cls(**filtered)
