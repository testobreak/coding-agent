# planning/planner.py
#
# Planner. Processes compiled ContextPackage and constructs high-level 
# IntentPlans representing the reasoning logic and objectives.

import json
from typing import Dict, Any
from context.context_package import ContextPackage
from llm.ollama_client import OllamaClient

class Planner:
    def __init__(self, llm=None):
        self.llm = llm or OllamaClient()

    def create_intent_plan(self, context: ContextPackage) -> Dict[str, Any]:
        """
        Determines the intent plan from the compiled ContextPackage.
        Uses Ollama to generate a structured JSON intent plan, with a rule-based fallback.
        """
        target_file = None
        if context.target_symbols:
            target_file = context.target_symbols[0].file_path
        elif context.related_files:
            target_file = context.related_files[0]
            
        fallback_plan = {
            "objective": context.intent.action,
            "targets": [context.intent.target] if context.intent.target != "unknown" else [],
            "required_changes": [context.intent.domain] if context.intent.domain != "unknown" else ["modification"],
            "verification": ["unit_tests"],
            "target_file": target_file,
            "failures": context.previous_attempts
        }

        # Try querying Ollama
        try:
            target_sym_desc = ", ".join(f"{s.name} ({s.file_path})" for s in context.target_symbols) if context.target_symbols else "None"
            related_files_desc = ", ".join(context.related_files) if context.related_files else "None"
            failures_desc = "\n".join(f"- {attempt}" for attempt in context.previous_attempts) if context.previous_attempts else "None"
            
            prompt = f"""You are a reasoning planner for an autonomous coding agent.
Analyze the goal and codebase context to produce a high-level intent plan in JSON format.

GOAL: {context.goal}

TARGET SYMBOLS:
{target_sym_desc}

RELATED FILES:
{related_files_desc}

PREVIOUS FAILURES/CRITICS:
{failures_desc}

Generate a JSON object with exactly the following keys:
1. "objective": A concise verb phrase describing what needs to be done (e.g., "Add audit logging", "Fix NullPointerException").
2. "targets": A list of symbol names or file paths that need modification (e.g. ["EmployeeService.saveEmployee"]).
3. "required_changes": A list of change types (e.g. ["logging", "null_check", "rest_endpoint"]).
4. "verification": A list of verification methods (e.g. ["unit_tests", "build_check"]).

Return ONLY the JSON object. Do not include any explanation or markdown formatting outside of JSON.
"""
            print("[Planner] Requesting high-level intent plan from LLM...")
            response = self.llm.chat([
                {"role": "user", "content": prompt}
            ])
            
            # Clean response if markdown block exists
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
            
            # Validate required keys
            required_keys = ["objective", "targets", "required_changes", "verification"]
            if all(k in parsed for k in required_keys):
                print(f"[Planner] Successfully generated LLM intent plan: {parsed}")
                parsed["target_file"] = target_file
                parsed["failures"] = context.previous_attempts
                return parsed
            else:
                print(f"[Planner] LLM response missing required keys. Falling back.")
        except Exception as e:
            print(f"[Planner] LLM intent generation failed or timed out: {e}. Using rule-based fallback.")
            
        return fallback_plan
