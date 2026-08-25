from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx


class OllamaError(RuntimeError):
    pass


class OllamaService:
    def __init__(
        self,
        base_url: str,
        default_model: str,
        compare_model: str,
        context: int,
        max_tokens: int,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.compare_model = compare_model
        self.context = context
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    async def chat(self, text: str, image_path: Path | None, compare: bool = False) -> tuple[str, str, dict[str, Any]]:
        model = self.compare_model if compare else self.default_model
        message: dict[str, Any] = {"role": "user", "content": text}
        if image_path:
            message["images"] = [base64.b64encode(image_path.read_bytes()).decode("ascii")]
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a concise bilingual desktop assistant running locally on a Raspberry Pi. "
                        "Reply in the user's language. When an image is supplied, describe only visible evidence "
                        "and state uncertainty instead of inventing details. Follow the user's requested output "
                        "format and length exactly. For simple requests, answer in one sentence. Do not volunteer "
                        "capability descriptions or limitations unless the user asks. Keep the answer under 160 words."
                    ),
                },
                message,
            ],
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {"num_ctx": self.context, "num_predict": self.max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            detail = getattr(exc.response, "text", "") if isinstance(exc, httpx.HTTPStatusError) else str(exc)
            raise OllamaError(f"Ollama request failed: {detail}") from exc
        data = response.json()
        content = str(data.get("message", {}).get("content", "")).strip()
        if not content:
            raise OllamaError("Ollama returned an empty response")
        stats = {
            key: data.get(key)
            for key in ("total_duration", "load_duration", "prompt_eval_count", "eval_count", "eval_duration")
            if data.get(key) is not None
        }
        return content, model, stats

    async def unload(self, model: str | None = None) -> None:
        payload = {"model": model or self.default_model, "keep_alive": 0}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(f"{self.base_url}/api/generate", json=payload)
        except httpx.HTTPError:
            return
