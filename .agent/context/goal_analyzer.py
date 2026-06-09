# context/goal_analyzer.py
#
# Goal Intent Analysis logic. Parses human queries into GoalIntent representation.

import re
from context.context_package import GoalIntent

class GoalAnalyzer:
    def analyze(self, goal: str) -> GoalIntent:
        goal_lower = goal.lower()
        
        # Determine action
        if any(w in goal_lower for w in ["fix", "bug", "error", "issue", "broken", "failure", "repair", "crash"]):
            action = "modify"
        elif any(w in goal_lower for w in ["refactor", "cleanup", "optimize", "improve"]):
            action = "refactor"
        elif any(w in goal_lower for w in ["add", "implement", "create", "feature", "build", "logging"]):
            action = "add_feature"
        elif any(w in goal_lower for w in ["analyze", "explain", "understand", "review", "summary", "summarize"]):
            action = "analyze"
        else:
            action = "unknown"

        # Extract CamelCase/dotted names as potential target
        target = "unknown"
        camel_case = re.findall(r'\b[A-Z][a-zA-Z0-9_]*\b', goal)
        dotted = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_\.]*\.[A-Z][a-zA-Z0-9_]*\b', goal)
        
        # Filter out common query verbs/keywords from target candidates
        action_keywords = {"add", "fix", "create", "implement", "refactor", "remove", "delete", "update", "modify", "logging", "to"}
        filtered_camel_case = [token for token in camel_case if token.lower() not in action_keywords]
        
        if dotted:
            target = dotted[0]
        elif filtered_camel_case:
            target = filtered_camel_case[0]
        elif camel_case:
            target = camel_case[0]

        # Determine domain from suffix or common terminology
        domain = "unknown"
        target_lower = target.lower()
        if "service" in target_lower:
            domain = "service"
        elif "controller" in target_lower:
            domain = "controller"
        elif "repository" in target_lower or "dao" in target_lower:
            domain = "repository"
        elif "dto" in target_lower or "model" in target_lower or "entity" in target_lower:
            domain = "model"
        
        return GoalIntent(
            action=action,
            target=target,
            domain=domain,
            confidence=0.90 if target != "unknown" else 0.50
        )
