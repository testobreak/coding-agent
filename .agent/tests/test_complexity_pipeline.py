# tests/test_complexity_pipeline.py

import unittest
from unittest.mock import patch, MagicMock

from runtime.runtime import Runtime
from routing.intent_router import RouteDecision, ExecutionMode, CostTier
from context.context_router import ContextBuilderEnum
from planning.task_types import TaskType as PlanningTaskType

class TestComplexityPipeline(unittest.TestCase):

    @patch("runtime.fast_path_router.FastPathRouter.route")
    @patch("llm.ollama_client.OllamaClient.chat")
    def test_mode_0_assist_pipeline(self, mock_chat, mock_route):
        # 1. Mock routing to ASSIST
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.ASSIST,
            context_mode=ContextBuilderEnum.REPOSITORY,
            confidence=0.95,
            reason="Assist test",
            cost_tier=CostTier.CHEAP
        )
        # Mock LLM chat response
        mock_chat.return_value = "This is the assist answer description."

        runtime = Runtime()
        # Mock ContextBuilder to return a mock context
        mock_context = MagicMock()
        mock_context.related_files = []
        mock_context.retrieved_chunks = []
        with patch("context.context_builder.ContextBuilder.build_planning_context", return_value=mock_context):
            runtime.run_goal("explain active file")

        # Verify LLM was queried with CHAT task type
        from inference.router import TaskType
        mock_chat.assert_called_once()
        self.assertEqual(mock_chat.call_args[1].get("task_type"), TaskType.CHAT)

        # Verify state contains completed virtual plan
        plan = runtime.state_manager.get_execution_plan()
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].id, "assist-task")
        self.assertEqual(plan.tasks[0].type, PlanningTaskType.RETRIEVE_CONTEXT)
        self.assertEqual(plan.tasks[0].description, "This is the assist answer description.")
        self.assertEqual(plan.tasks[0].outputs["response"], "This is the assist answer description.")
        self.assertEqual(runtime.state_manager.get_execution_state(), "COMPLETED")

    @patch("runtime.fast_path_router.FastPathRouter.route")
    def test_mode_1_edit_pipeline(self, mock_route):
        # 2. Mock routing to PATCH_EDIT (Mode 1)
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.PATCH_EDIT,
            context_mode=ContextBuilderEnum.SELECTION,
            confidence=0.95,
            reason="Simple edit test",
            cost_tier=CostTier.CHEAP
        )

        runtime = Runtime()
        
        # Mock context package
        mock_context = MagicMock()
        mock_context.goal = "rename x to y"
        mock_context.primary_symbol = None
        mock_context.related_files = ["src/test.py"]
        mock_context.retrieved_chunks = []

        # Patch build_planning_context & self.engine.run (so we don't execute actual file updates)
        with patch("context.context_builder.ContextBuilder.build_planning_context", return_value=mock_context), \
             patch.object(runtime.engine, "run") as mock_engine_run:
            
            runtime.run_goal("rename x to y")

        # Verify that only modify tasks exist in the plan (no commit/build/test)
        plan = runtime.state_manager.get_execution_plan()
        self.assertIsNotNone(plan)
        task_types = [t.type for t in plan.tasks]
        self.assertIn(PlanningTaskType.MODIFY_SYMBOL, task_types)
        self.assertNotIn(PlanningTaskType.COMMIT_TRANSACTION, task_types)
        self.assertNotIn(PlanningTaskType.VERIFY_BUILD, task_types)
        self.assertNotIn(PlanningTaskType.RUN_TEST, task_types)

    @patch("runtime.fast_path_router.FastPathRouter.route")
    def test_mode_2_agent_pipeline(self, mock_route):
        # 3. Mock routing to AGENT (Mode 2)
        mock_route.return_value = RouteDecision(
            execution_mode=ExecutionMode.AGENT,
            context_mode=ContextBuilderEnum.AGENT,
            confidence=0.95,
            reason="Complex agent test",
            cost_tier=CostTier.EXPENSIVE
        )

        runtime = Runtime()
        
        # Mock context package
        mock_context = MagicMock()
        mock_context.goal = "implement complex features"
        mock_context.primary_symbol = None
        mock_context.related_files = ["src/main.py"]
        mock_context.retrieved_chunks = []

        # Create a real serializable ExecutionPlan
        from planning.execution_plan import ExecutionPlan, ExecutionStage
        from planning.task_node import TaskNode
        from planning.task_status import TaskStatus
        from planning.task_types import TaskType as PlanningTaskType

        task_node = TaskNode(
            id="agent-task",
            type=PlanningTaskType.VERIFY_BUILD,
            description="Verify build",
            status=TaskStatus.COMPLETED
        )
        mock_plan = ExecutionPlan(
            goal="implement complex features",
            plan_id="test-plan",
            tasks=[task_node],
            stages=[ExecutionStage(stage_id="stage-1", parallel_tasks=["agent-task"])]
        )

        with patch("context.context_builder.ContextBuilder.build_planning_context", return_value=mock_context), \
             patch("planning.plan_compiler.PlanCompiler.compile", return_value=mock_plan) as mock_compile, \
             patch("planning.plan_validator.PlanValidator.validate", return_value=[]), \
             patch.object(runtime.engine, "run"):
            
            runtime.run_goal("implement complex features")
            
            # Verify compiler was used to construct full plan
            mock_compile.assert_called_once()


if __name__ == "__main__":
    unittest.main()
