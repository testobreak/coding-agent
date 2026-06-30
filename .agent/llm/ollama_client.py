# llm/ollama_client.py

import requests

from requests.exceptions import (
    ConnectionError,
    Timeout,
    RequestException
)


class OllamaClient:

    DEFAULT_TIMEOUT = 120

    def __init__(
        self,
        model="qwen2.5-coder:7b",
        host="http://localhost:11434"
    ):

        self.model = model

        self.host = host.rstrip("/")
        from inference.router import ModelRouter
        self.router = ModelRouter(host=self.host, default_model=self.model)

    def speculative_chat(
        self,
        messages,
        task_type=None,
        on_progress=None,
        *args,
        **kwargs
    ):
        """
        Runs speculative decoding chat by resolving target and draft models.
        """
        target_model = self.model
        if task_type is not None:
            from inference.router import TaskType
            if isinstance(task_type, TaskType):
                target_model = self.router.route(task_type)

        from inference.router import TaskType
        draft_model = self.router.route(TaskType.RETRIEVAL)

        if target_model == draft_model:
            return self.chat(messages, task_type=task_type, *args, **kwargs)

        target_client = OllamaClient(model=target_model, host=self.host)
        draft_client = OllamaClient(model=draft_model, host=self.host)

        from inference.speculative import SpeculativeDecoder
        decoder = SpeculativeDecoder(target_client=target_client, draft_client=draft_client)

        prompt = messages[-1]["content"] if messages else ""
        context = ""
        if len(messages) > 1:
            context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages[:-1]])

        return decoder.generate_speculative_line(prompt=prompt, context=context, on_progress=on_progress)

    def chat(
        self,
        messages,
        task_type=None,
        stream=False,
        *args,
        **kwargs
    ):

        model_to_use = self.model
        if task_type is not None:
            from inference.router import TaskType
            if isinstance(task_type, TaskType):
                model_to_use = self.router.route(task_type)

        try:
            if stream:
                response = requests.post(
                    f"{self.host}/api/chat",
                    json={
                        "model":
                            model_to_use,
                        "messages":
                            messages,
                        "stream":
                            True
                    },
                    stream=True,
                    timeout=self.DEFAULT_TIMEOUT
                )
                response.raise_for_status()

                def token_generator():
                    import json
                    for line in response.iter_lines():
                        if line:
                            try:
                                chunk = json.loads(line.decode('utf-8'))
                                content = chunk.get("message", {}).get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                pass
                return token_generator()

            response = requests.post(

                f"{self.host}/api/chat",

                json={

                    "model":
                        model_to_use,

                    "messages":
                        messages,

                    "stream":
                        False
                },

                timeout=self.DEFAULT_TIMEOUT
            )

            response.raise_for_status()

        except ConnectionError as exc:

            raise RuntimeError(
                "Unable to connect to Ollama. "
                "Ensure the Ollama server is running."
            ) from exc

        except Timeout as exc:

            raise RuntimeError(
                f"Ollama request exceeded "
                f"{self.DEFAULT_TIMEOUT} seconds."
            ) from exc

        except RequestException as exc:

            raise RuntimeError(
                f"Ollama request failed: {exc}"
            ) from exc

        #
        # JSON parsing
        #

        try:

            data = response.json()

        except ValueError as exc:

            raise RuntimeError(
                "Ollama returned invalid JSON."
            ) from exc

        #
        # Response validation
        #

        message = data.get(
            "message"
        )

        if not isinstance(
            message,
            dict
        ):

            raise RuntimeError(
                "Ollama response missing "
                "'message' object."
            )

        content = message.get(
            "content"
        )

        if content is None:

            raise RuntimeError(
                "Ollama response missing "
                "'content'."
            )

        return str(content)

    # =====================================================
    # HEALTH CHECK
    # =====================================================

    def ping(
        self
    ):

        try:

            response = requests.get(

                f"{self.host}/api/tags",

                timeout=10
            )

            return (
                response.status_code == 200
            )

        except Exception:

            return False
