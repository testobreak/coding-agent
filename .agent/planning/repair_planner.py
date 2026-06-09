# planning/repair_planner.py
#
# Repair Planner. Analyzes VerificationResult diagnostics and formulates
# repair TaskNodes specifically targeting imports, compilation errors, and test failures.

import json
from typing import List, Dict, Any, Optional
from execution.verification_result import VerificationResult, Diagnostic
from planning.task_node import TaskNode
from planning.task_types import TaskType
from planning.task_status import TaskStatus
from llm.ollama_client import OllamaClient

class RepairPlanner:
    def __init__(self, llm=None):
        self.llm = llm or OllamaClient()

    def plan_repairs(self, result: VerificationResult, goal: str) -> List[TaskNode]:
        """
        Formulates a list of repair TaskNodes based on VerificationResult diagnostics.
        """
        if result.success or not result.diagnostics:
            return []
            
        print(f"[RepairPlanner] Planning repairs for {len(result.diagnostics)} diagnostics...")
        
        # Try LLM repair planning first
        try:
            diags_desc = []
            for d in result.diagnostics:
                diags_desc.append({
                    "type": d.type,
                    "file_path": d.file_path,
                    "line": d.line,
                    "symbol": d.symbol,
                    "message": d.message
                })
                
            prompt = f"""You are a repository-aware software engineering agent specializing in auto-repairing build and test failures.
Analyze the following diagnostics and plan repair actions:

GOAL: {goal}

DIAGNOSTICS:
{json.dumps(diags_desc, indent=2)}

Generate a JSON object containing exactly one key "repairs", which is a list of repair actions.
Each action must have:
1. "type": One of "repair_imports", "repair_compilation", "repair_symbol".
2. "target": The file path or symbol name to edit.
3. "description": A concise description of the required repair (e.g., "Add import java.util.List;", "Fix variable name spelling").

Return ONLY the JSON object. Do not include any markdown format (such as ```json ... ```) or explanation.
"""
            response = self.llm.chat([
                {"role": "user", "content": prompt}
            ])
            
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines:
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
                
            parsed = json.loads(cleaned)
            repairs = parsed.get("repairs", [])
            
            tasks = []
            for i, rep in enumerate(repairs):
                rep_type_str = rep.get("type", "repair_symbol")
                # Map string type to TaskType enum
                if rep_type_str == "repair_imports":
                    t_type = TaskType.REPAIR_IMPORTS
                elif rep_type_str == "repair_compilation":
                    t_type = TaskType.REPAIR_COMPILATION
                else:
                    t_type = TaskType.REPAIR_SYMBOL
                    
                tasks.append(TaskNode(
                    id=f"repair_{i}_{t_type.value}",
                    type=t_type,
                    target_symbol=rep.get("target"),
                    description=rep.get("description", "Fix build error"),
                    dependencies=[],
                    payload={"file_path": rep.get("target")}
                ))
            
            if tasks:
                print(f"[RepairPlanner] Successfully generated LLM repair plan with {len(tasks)} tasks.")
                return tasks
        except Exception as e:
            print(f"[RepairPlanner] LLM repair planning failed or timed out: {e}. Using rule-based fallback.")
            
        # Rule-based fallback
        tasks = []
        for i, d in enumerate(result.diagnostics):
            msg_lower = d.message.lower()
            if "import" in msg_lower or "cannot resolve symbol" in msg_lower or "cannot find symbol" in msg_lower:
                t_type = TaskType.REPAIR_IMPORTS
                desc = f"Fix missing/incorrect imports in {d.file_path}"
            elif "syntax" in d.type or "syntax error" in msg_lower:
                t_type = TaskType.REPAIR_SYMBOL
                desc = f"Fix syntax errors in {d.file_path}"
            else:
                t_type = TaskType.REPAIR_COMPILATION
                desc = f"Fix compilation/build failure in {d.file_path} at line {d.line}"
                
            tasks.append(TaskNode(
                id=f"repair_fallback_{i}",
                type=t_type,
                target_symbol=d.symbol or d.file_path,
                description=desc,
                dependencies=[],
                payload={"file_path": d.file_path, "line": d.line, "message": d.message}
            ))
            
        return tasks
