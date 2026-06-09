# execution/action_compiler.py

from typing import List

from planning.action_schema import (
    Action
)

from planning.action_types import *

from execution.executable_action import (
    ExecutableAction
)


class ActionCompiler:

    # =====================================================
    # MAIN
    # =====================================================

    def compile(
        self,
        actions: List[Action]
    ) -> List[ExecutableAction]:

        compiled = []

        for action in actions:

            compiled.extend(
                self.expand_action(
                    action
                )
            )

        return self.sort_by_priority(
            compiled
        )

    # =====================================================
    # EXPANSION
    # =====================================================

    def expand_action(
        self,
        action: Action
    ):

        action_type = (
            action.action_type
        )

        # =============================================
        # RETRIEVE
        # =============================================

        if action_type == RETRIEVE:

            return [

                self.build_action(

                    tool="semantic_retrieve",

                    action=action,

                    args={
                        "query":
                            action.target
                            or ""
                    }
                )
            ]

        # =============================================
        # ANALYZE
        # =============================================

        elif action_type == ANALYZE:

            return [

                self.build_action(

                    tool="list_files",

                    action=action
                )
            ]

        # =============================================
        # MODIFY
        # =============================================

        elif action_type == MODIFY:

            return [
                self.build_action(
                    tool="modify_symbol",
                    action=action,
                    args={
                        "symbol": action.target or "unknown",
                        "path": action.file_path,
                        "goal": action.reasoning or ""
                    }
                )
            ]

        # =============================================

        # PATCH

        # =============================================

        elif action_type == PATCH:

            return [

                self.build_action(

                    tool="apply_patch",

                    action=action,

                    args=action.metadata or {}
                )
            ]

        # =============================================
        # WRITE FILE
        # =============================================

        elif action_type == WRITE_FILE:

            return [

                self.build_action(

                    tool="write_file",

                    action=action,

                    args=action.metadata or {}
                )
            ]

        # =============================================
        # GENERATE PATCH
        # =============================================

        elif action_type == GENERATE_PATCH:

            return [

                self.build_action(

                    tool="generate_patch",

                    action=action,

                    args=action.metadata or {}
                )
            ]

        # =============================================
        # GENERATE MODIFICATION
        # =============================================

        elif action_type == GENERATE_MODIFICATION:

            return [

                self.build_action(

                    tool="generate_modification",

                    action=action,

                    args=action.metadata or {}
                )
            ]

        # =============================================
        # VALIDATE
        # =============================================

        elif action_type == VALIDATE:

            return [

                self.build_action(
                    tool="git_diff",
                    action=action,
                    priority_boost=-2
                ),

                self.build_action(
                    tool="run_backend_tests",
                    action=action,
                    priority_boost=-1
                ),

                self.build_action(
                    tool="run_frontend_build",
                    action=action
                )
            ]

        # =============================================

        # TEST

        # =============================================

        elif action_type == TEST:

            return [

                self.build_action(

                    tool="run_backend_tests",

                    action=action
                )
            ]

        # =============================================
        # RUN BACKEND TESTS
        # =============================================

        elif action_type == RUN_BACKEND_TESTS:

            return [

                self.build_action(

                    tool="run_backend_tests",

                    action=action
                )
            ]

        # =============================================
        # RUN FRONTEND TESTS
        # =============================================

        elif action_type == RUN_FRONTEND_TESTS:

            return [

                self.build_action(

                    tool="run_frontend_tests",

                    action=action
                )
            ]

        # =============================================
        # RUN FRONTEND BUILD
        # =============================================

        elif action_type == RUN_FRONTEND_BUILD:

            return [

                self.build_action(

                    tool="run_frontend_build",

                    action=action
                )
            ]

        # =============================================
        # GIT STATUS
        # =============================================

        elif action_type == GIT_STATUS:

            return [

                self.build_action(

                    tool="git_status",

                    action=action
                )
            ]

        # =============================================
        # GIT DIFF
        # =============================================

        elif action_type == GIT_DIFF:

            return [

                self.build_action(

                    tool="git_diff",

                    action=action
                )
            ]

        # =============================================
        # ROLLBACK
        # =============================================

        elif action_type == ROLLBACK:

            if not action.file_path:

                return []

            return [

                self.build_action(

                    tool="rollback_file",

                    action=action,

                    args={
                        "path":
                            action.file_path
                    }
                )
            ]

        # =============================================
        # REPAIR
        # =============================================

        elif action_type == REPAIR:

            executions = []

            #
            # Rebuild failure context
            #
            executions.append(

                self.build_action(

                    tool="semantic_retrieve",

                    action=action,

                    args={
                        "query":
                            action.target
                            or action.reasoning
                            or "repair failure"
                    },

                    priority_boost=-2
                )
            )

            #
            # Attempt repair on known targets
            #
            repair_targets = (
                action.metadata.get(
                    "targets",
                    []
                )
            )

            for path in repair_targets:

                executions.append(

                    self.build_action(

                        tool="modify_symbol",

                        action=action,

                        args={
                            "symbol": action.target or "unknown",
                            "path": path,
                            "goal": action.reasoning or "repair failure"
                        },

                        priority_boost=-1
                    )
                )

            #
            # Validate repair
            #
            executions.append(

                self.build_action(
                    tool="git_diff",
                    action=action
                )
            )

            #
            # Re-run tests
            #
            executions.append(

                self.build_action(
                    tool="run_backend_tests",
                    action=action
                )
            )

            return executions

        # =============================================

        # SUMMARIZE

        # =============================================

        elif action_type == SUMMARIZE:

            return [

                self.build_action(

                    tool="summarize_state",

                    action=action
                )
            ]

        # =============================================
        # MODIFICATION PLANNING
        # =============================================

        elif action_type == MODIFICATION_PLANNING:

            return [

                self.build_action(

                    tool="plan_modifications",

                    action=action
                )
            ]

        # =============================================
        # REFLECT
        # =============================================

        elif action_type == REFLECT:

            return [

                self.build_action(

                    tool="reflect",

                    action=action
                )
            ]

        # =============================================
        # REPLAN
        # =============================================

        elif action_type == REPLAN:

            return [

                self.build_action(

                    tool="replan",

                    action=action
                )
            ]

        # =============================================
        # UNKNOWN ACTION
        # =============================================

        raise RuntimeError(

            f"Unsupported action type: "
            f"{action_type}"
        )

    # =====================================================
    # BUILD
    # =====================================================

    def build_action(
        self,
        tool,
        action,
        args=None,
        priority_boost=0
    ):

        return ExecutableAction(

            tool=tool,

            args=args or {},

            priority=max(
                0,
                action.priority
                + priority_boost
            ),

            blocking=action.blocking,

            max_retries=(
                action.max_retries
            ),

            metadata={

                "source_action_id":
                    action.action_id,

                "source_action_type":
                    action.action_type,

                "reasoning":
                    action.reasoning,

                "estimated_impact":
                    action.estimated_impact
            }
        )

    # =====================================================
    # SORTING
    # =====================================================

    def sort_by_priority(
        self,
        actions
    ):

        return sorted(

            actions,

            key=lambda x: (

                x.priority,

                x.retries
            )
        )
