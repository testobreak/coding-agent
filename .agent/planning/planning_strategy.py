# planning/planning_strategy.py
#
# PlanningStrategy enum. Deterministically selects the DAG template
# based on GoalIntent action and ContextPackage risk characteristics.

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context.context_package import ContextPackage


class PlanningStrategy(Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST_ONLY = "test_only"
    ANALYSIS = "analysis"
    REPAIR = "repair"

    @staticmethod
    def from_context(ctx: "ContextPackage") -> "PlanningStrategy":
        """
        Deterministically selects a planning strategy from the ContextPackage.

        Decision tree:
          1. If previous_attempts exist → REPAIR  (we already failed once)
          2. Intent action mapping:
               modify / fix / bug   → BUGFIX
               add_feature / create → FEATURE
               refactor             → REFACTOR
               analyze              → ANALYSIS
               test                 → TEST_ONLY
          3. Fallback               → FEATURE
        """
        # 1. Repair path: prior failures detected
        if ctx.previous_attempts:
            return PlanningStrategy.REPAIR

        # 2. Intent-driven selection
        action = ""
        if ctx.intent:
            action = (ctx.intent.action or "").lower()

        if action in ("modify", "fix", "bug", "debug"):
            return PlanningStrategy.BUGFIX
        elif action in ("add_feature", "create", "implement", "add"):
            return PlanningStrategy.FEATURE
        elif action in ("refactor", "cleanup", "optimize"):
            return PlanningStrategy.REFACTOR
        elif action in ("analyze", "explain", "review", "summary"):
            return PlanningStrategy.ANALYSIS
        elif action in ("test", "test_only"):
            return PlanningStrategy.TEST_ONLY

        # 3. Fallback
        return PlanningStrategy.FEATURE
