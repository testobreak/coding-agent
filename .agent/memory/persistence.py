# memory/persistence.py

import json
import shutil
import tempfile

from pathlib import Path

from dataclasses import (
    asdict
)

from memory.task_state import (
    TaskState
)

from memory.runtime_memory import (
    RuntimeMemory
)


class StatePersistence:

    VERSION = 1

    def __init__(
        self,
        tasks_dir="tasks"
    ):

        self.tasks_dir = Path(
            tasks_dir
        )

        self.tasks_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    # =====================================================
    # PATHS
    # =====================================================

    def get_task_path(
        self,
        task_id
    ):

        return (
            self.tasks_dir /
            f"{task_id}.json"
        )

    # =====================================================
    # SAVE
    # =====================================================

    def save(
        self,
        state: TaskState,
        task_id: str
    ):

        path = self.get_task_path(
            task_id
        )

        backup_path = path.with_suffix(
            ".backup.json"
        )

        payload = asdict(state)

        payload["_version"] = (
            self.VERSION
        )

        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp"
        )

        try:

            with open(
                temp_path,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    payload,
                    f,
                    indent=2,
                    ensure_ascii=False
                )

            if path.exists():

                shutil.copy2(
                    path,
                    backup_path
                )

            shutil.move(
                temp_path,
                path
            )

        finally:

            temp = Path(temp_path)

            if temp.exists():

                temp.unlink(
                    missing_ok=True
                )

    # =====================================================
    # LOAD
    # =====================================================

    def load(
        self,
        task_id: str
    ) -> TaskState:

        path = self.get_task_path(
            task_id
        )

        if not path.exists():

            raise FileNotFoundError(
                f"Task not found: {task_id}"
            )

        try:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

        except Exception:

            backup = path.with_suffix(
                ".backup.json"
            )

            if not backup.exists():

                raise RuntimeError(
                    "State corrupted and "
                    "backup missing."
                )

            with open(
                backup,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

        # =================================================
        # VERSION VALIDATION
        # =================================================

        version = data.pop(
            "_version",
            1
        )

        if version > self.VERSION:

            raise RuntimeError(
                f"Unsupported state version: "
                f"{version}. "
                f"Current version: "
                f"{self.VERSION}"
            )

        # =================================================
        # RUNTIME MEMORY MIGRATION
        # =================================================

        runtime_memory = data.get(
            "runtime_memory"
        )

        #
        # Older persisted states may not contain
        # runtime_memory at all.
        #
        if runtime_memory is None:

            data["runtime_memory"] = (
                RuntimeMemory()
            )

        #
        # Persisted RuntimeMemory dict
        #
        elif isinstance(
            runtime_memory,
            dict
        ):

            try:

                data["runtime_memory"] = (
                    RuntimeMemory(
                        **runtime_memory
                    )
                )

            except TypeError:

                #
                # Schema drift / corrupted state
                #
                data["runtime_memory"] = (
                    RuntimeMemory()
                )

        #
        # Invalid runtime_memory payload
        #
        else:

            data["runtime_memory"] = (
                RuntimeMemory()
            )

        return TaskState(**data)

    # =====================================================
    # EXISTS
    # =====================================================

    def exists(
        self,
        task_id: str
    ):

        return self.get_task_path(
            task_id
        ).exists()

    # =====================================================
    # DELETE
    # =====================================================

    def delete(
        self,
        task_id: str
    ):

        path = self.get_task_path(
            task_id
        )

        if path.exists():

            path.unlink()

    # =====================================================
    # LIST
    # =====================================================

    def list_tasks(self):

        return sorted(

            path.stem

            for path in self.tasks_dir.glob(
                "*.json"
            )

            if not path.name.endswith(
                ".backup.json"
            )
        )
