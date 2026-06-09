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

    def chat(
        self,
        messages
    ):

        try:

            response = requests.post(

                f"{self.host}/api/chat",

                json={

                    "model":
                        self.model,

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
