# inference/ollama_client.py
"""
High-performance local Ollama client optimized for constrained local LLMs (e.g. Apple Silicon M1).
Features:
- keep_alive persistence to avoid model reloading
- Native telemetry extraction (tokens/sec, prompt eval ms, generation ms)
- Streaming and non-streaming modes
"""

import time
import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, Generator


@dataclass
class OllamaTelemetry:
    model: str
    prompt_tokens: int = 0
    prompt_eval_duration_ms: float = 0.0
    output_tokens: int = 0
    generation_duration_ms: float = 0.0
    tokens_per_second: float = 0.0
    load_duration_ms: float = 0.0
    total_duration_ms: float = 0.0

    def summary(self) -> str:
        return (
            f"Model: {self.model} | "
            f"Prompt: {self.prompt_tokens} toks ({self.prompt_eval_duration_ms:.1f}ms) | "
            f"Output: {self.output_tokens} toks ({self.generation_duration_ms:.1f}ms) | "
            f"Speed: {self.tokens_per_second:.1f} tok/s | "
            f"Total: {self.total_duration_ms:.1f}ms"
        )


@dataclass
class OllamaResponse:
    text: str
    telemetry: OllamaTelemetry
    raw_response: Dict[str, Any] = field(default_factory=dict)


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        keep_alive: str = "30m",
        timeout_seconds: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keep_alive = keep_alive
        self.timeout_seconds = timeout_seconds

    def check_health(self) -> bool:
        """Verifies Ollama daemon is reachable and model is available."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as res:
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    models = [m.get("name") for m in data.get("models", [])]
                    # Model match can be full name or prefix
                    return any(self.model in m or m.startswith(self.model) for m in models)
        except Exception:
            return False
        return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        num_ctx: int = 4096,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> OllamaResponse:
        """
        Executes a completion request against local Ollama.
        If stream_callback is provided, chunks of text are streamed in real-time.
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "keep_alive": self.keep_alive,
            "stream": stream_callback is not None,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        url = f"{self.base_url}/api/generate"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        start_time = time.time()
        final_data = {}

        if stream_callback:
            full_text = []
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                for line in resp:
                    if not line:
                        continue
                    chunk = json.loads(line.decode("utf-8"))
                    text_chunk = chunk.get("response", "")
                    if text_chunk:
                        full_text.append(text_chunk)
                        stream_callback(text_chunk)
                    if chunk.get("done"):
                        final_data = chunk
                        break
            generated_text = "".join(full_text)
        else:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                final_data = json.loads(resp.read().decode("utf-8"))
                generated_text = final_data.get("response", "")

        total_elapsed_ms = (time.time() - start_time) * 1000

        # Parse Ollama native timing counters (all durations in nanoseconds)
        prompt_tokens = final_data.get("prompt_eval_count", 0)
        output_tokens = final_data.get("eval_count", 0)
        prompt_eval_ms = final_data.get("prompt_eval_duration", 0) / 1e6
        eval_duration_ms = final_data.get("eval_duration", 0) / 1e6
        load_duration_ms = final_data.get("load_duration", 0) / 1e6

        tokens_per_sec = 0.0
        if eval_duration_ms > 0 and output_tokens > 0:
            tokens_per_sec = output_tokens / (eval_duration_ms / 1000.0)

        telemetry = OllamaTelemetry(
            model=self.model,
            prompt_tokens=prompt_tokens,
            prompt_eval_duration_ms=prompt_eval_ms,
            output_tokens=output_tokens,
            generation_duration_ms=eval_duration_ms,
            tokens_per_second=tokens_per_sec,
            load_duration_ms=load_duration_ms,
            total_duration_ms=total_elapsed_ms,
        )

        return OllamaResponse(
            text=generated_text,
            telemetry=telemetry,
            raw_response=final_data,
        )
