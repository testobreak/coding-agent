# runtime/recovery_loop.py

from reflection.replanner import (
    Replanner
)

from execution.action_compiler import (
    ActionCompiler
)


class RecoveryLoop:

    def __init__(
        self,
        state_manager,
        executor=None
    ):

        self.state_manager = (
            state_manager
        )

        self.executor = executor

        self.replanner = (
            Replanner()
        )

        self.compiler = (
            ActionCompiler()
        )

    # ==========================================
    # MAIN
    # ==========================================

    def run(self):

        state = (
            self.state_manager.get_state()
        )

        pipeline = self.executor.retrieval_pipeline if self.executor else None

        new_actions = (
            self.replanner.replan(
                state,
                retrieval_pipeline=pipeline
            )
        )

        if not new_actions:

            return False

        executions = (
            self.compiler.compile(
                new_actions
            )
        )

        self.state_manager.push_executions(
            executions
        )

        return True
