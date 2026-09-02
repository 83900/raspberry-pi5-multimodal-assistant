from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path


class VisionIntentError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VisionIntentDecision:
    capture: bool
    probability: float
    threshold: float


class VisionIntentService:
    def __init__(
        self,
        model_dir: Path,
        *,
        threshold: float | None = None,
        threads: int = 2,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.model_dir = model_dir
        self.threshold = threshold
        self.threads = threads
        self.timeout_seconds = timeout_seconds

    async def classify(self, text: str) -> VisionIntentDecision:
        required = ("model.onnx", "tokenizer.json", "vision_intent_head.npz")
        missing = [name for name in required if not (self.model_dir / name).is_file()]
        if missing:
            raise VisionIntentError(f"vision intent files missing: {', '.join(missing)}")

        command = [
            sys.executable,
            "-m",
            "pi_edge_assistant.vision_intent_worker",
            "--model-dir",
            str(self.model_dir),
            "--threads",
            str(self.threads),
        ]
        if self.threshold is not None:
            command.extend(("--threshold", str(self.threshold)))

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(text.encode("utf-8")), self.timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise VisionIntentError("vision intent inference timed out") from exc
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip().splitlines()
            raise VisionIntentError(detail[-1][:500] if detail else "vision intent inference failed")
        try:
            payload = json.loads(stdout)
            return VisionIntentDecision(
                capture=bool(payload["capture"]),
                probability=float(payload["probability"]),
                threshold=float(payload["threshold"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise VisionIntentError("vision intent worker returned invalid output") from exc
