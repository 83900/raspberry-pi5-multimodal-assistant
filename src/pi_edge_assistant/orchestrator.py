from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import HistoryStore
from .events import EventHub
from .models import AssistantState, InteractionRecord, JobResult, RuntimeStatus


logger = logging.getLogger(__name__)


VISION_TRIGGERS = (
    "看看",
    "看一下",
    "拍照",
    "拍张",
    "画面",
    "照片",
    "摄像头",
    "眼前",
    "what do you see",
    "look at",
    "camera",
    "photo",
    "snapshot",
    "image",
    "picture",
)


def requests_vision(text: str) -> bool:
    normalized = text.casefold()
    return any(trigger in normalized for trigger in VISION_TRIGGERS)


class BusyError(RuntimeError):
    pass


class Orchestrator:
    def __init__(
        self,
        *,
        audio: Any,
        camera: Any,
        asr: Any,
        ollama: Any,
        tts: Any,
        metrics: Any,
        media: Any,
        history: HistoryStore,
        events: EventHub,
        tts_enabled: bool,
        vision_intent: Any | None = None,
    ) -> None:
        self.audio = audio
        self.camera = camera
        self.asr = asr
        self.ollama = ollama
        self.tts = tts
        self.metrics = metrics
        self.media = media
        self.history = history
        self.events = events
        self.tts_enabled = tts_enabled
        self.vision_intent = vision_intent
        self.status = RuntimeStatus(model=ollama.default_model)
        self._interaction_lock = asyncio.Lock()
        self._recording_job_id: str | None = None
        self._recording_include_image = False
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._jobs: dict[str, JobResult] = {}

    async def start_recording(self, include_image: bool) -> str:
        if self._interaction_lock.locked():
            raise BusyError("assistant is busy")
        await self._interaction_lock.acquire()
        job_id = uuid.uuid4().hex
        self._recording_job_id = job_id
        self._recording_include_image = include_image
        self._jobs[job_id] = JobResult(job_id=job_id)
        try:
            await self.audio.start_recording()
            await self._set_state(
                AssistantState.RECORDING,
                active_job_id=job_id,
                include_image=include_image,
                transcript="",
                response="",
                timings={},
                error=None,
                audio_urls=[],
            )
            return job_id
        except Exception:
            self._recording_job_id = None
            self._interaction_lock.release()
            raise

    async def stop_recording(self) -> str:
        job_id = self._recording_job_id
        if not job_id or self.status.state != AssistantState.RECORDING:
            raise RuntimeError("recording is not active")
        try:
            audio_path = await self.audio.stop_recording()
        except Exception as exc:
            await self.audio.cancel_recording()
            self._recording_job_id = None
            self._jobs[job_id] = JobResult(job_id=job_id, done=True, error=str(exc))
            if self._interaction_lock.locked():
                self._interaction_lock.release()
            await self._set_state(AssistantState.IDLE, active_job_id=None, error=str(exc))
            raise
        self._recording_job_id = None
        task = asyncio.create_task(
            self._run_interaction(
                job_id=job_id,
                input_mode="microphone",
                text=None,
                audio_path=audio_path,
                include_image=self._recording_include_image,
                compare=False,
                lock_held=True,
            )
        )
        self._track_task(job_id, task)
        return job_id

    async def submit_chat(self, text: str, include_image: bool, compare: bool) -> str:
        if self._interaction_lock.locked():
            raise BusyError("assistant is busy")
        await self._interaction_lock.acquire()
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = JobResult(job_id=job_id)
        task = asyncio.create_task(
            self._run_interaction(
                job_id=job_id,
                input_mode="text",
                text=text,
                audio_path=None,
                include_image=include_image,
                compare=compare,
                lock_held=True,
            )
        )
        self._track_task(job_id, task)
        return job_id

    def _track_task(self, job_id: str, task: asyncio.Task[None]) -> None:
        self._tasks[job_id] = task

        def done(_: asyncio.Task[None]) -> None:
            self._tasks.pop(job_id, None)

        task.add_done_callback(done)

    async def wait_for_job(self, job_id: str, timeout: float = 30) -> JobResult:
        task = self._tasks.get(job_id)
        if task:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return self._jobs[job_id]

    def job(self, job_id: str) -> JobResult | None:
        return self._jobs.get(job_id)

    async def _run_interaction(
        self,
        *,
        job_id: str,
        input_mode: str,
        text: str | None,
        audio_path: Path | None,
        include_image: bool,
        compare: bool,
        lock_held: bool,
    ) -> None:
        timings: dict[str, float] = {}
        image_path: Path | None = None
        transcript = text or ""
        response = ""
        model = self.ollama.compare_model if compare else self.ollama.default_model
        error_code: str | None = None
        peak_memory = 0.0
        started = time.perf_counter()
        try:
            await self._update(
                active_job_id=job_id,
                transcript=transcript,
                response="",
                include_image=include_image,
                timings={},
                error=None,
                audio_urls=[],
            )
            if audio_path:
                await self._set_state(AssistantState.TRANSCRIBING, active_job_id=job_id)
                stage = time.perf_counter()
                transcript, duration = await self.asr.transcribe(audio_path)
                timings["asr_seconds"] = round(time.perf_counter() - stage, 3)
                timings["audio_seconds"] = round(duration, 3)
                timings["asr_rtf"] = round(timings["asr_seconds"] / duration, 3) if duration else 0
                audio_path.unlink(missing_ok=True)
                audio_path = None
                await self._update(transcript=transcript, timings=timings)

            if not include_image:
                include_image = requests_vision(transcript)
            if not include_image and self.vision_intent is not None:
                stage = time.perf_counter()
                try:
                    decision = await self.vision_intent.classify(transcript)
                    timings["vision_intent_seconds"] = round(time.perf_counter() - stage, 3)
                    timings["vision_intent_probability"] = round(decision.probability, 4)
                    timings["vision_intent_threshold"] = round(decision.threshold, 4)
                    include_image = decision.capture
                except Exception as exc:
                    logger.warning("Vision intent classifier unavailable: %s", exc)
                    error_code = error_code or "vision_intent_unavailable"
                    await self.events.broadcast(
                        {"type": "warning", "job_id": job_id, "message": "视觉意图分类器不可用，本次按文本处理"}
                    )
            await self._update(include_image=include_image, timings=timings)
            if include_image:
                await self._set_state(AssistantState.CAPTURING)
                stage = time.perf_counter()
                try:
                    image_path = await self.camera.capture()
                    timings["capture_seconds"] = round(time.perf_counter() - stage, 3)
                    preview = "data:image/jpeg;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")
                    await self.events.broadcast({"type": "image", "job_id": job_id, "data_url": preview})
                except Exception as exc:
                    error_code = "camera_unavailable"
                    await self.events.broadcast({"type": "warning", "job_id": job_id, "message": str(exc)})

            await self._set_state(AssistantState.THINKING)
            stage = time.perf_counter()
            response, model, model_stats = await self.ollama.chat(transcript, image_path, compare=compare)
            timings["llm_seconds"] = round(time.perf_counter() - stage, 3)
            timings.update(self._ollama_timings(model_stats))
            await self._update(response=response, model=model, timings=timings)
            peak_memory = max(peak_memory, self._memory_used())

            if self.tts_enabled:
                await self._set_state(AssistantState.SPEAKING)
                stage = time.perf_counter()
                try:
                    paths = await self.tts.synthesize(response, job_id)
                    timings["tts_seconds"] = round(time.perf_counter() - stage, 3)
                    urls = [f"/api/audio/{job_id}/{path.name}" for path in paths]
                    await self._update(audio_urls=urls, timings=timings)
                    await self.events.broadcast({"type": "audio", "job_id": job_id, "urls": urls})
                    try:
                        await self.audio.play(paths)
                    except Exception as exc:
                        error_code = error_code or "playback_unavailable"
                        await self.events.broadcast({"type": "warning", "job_id": job_id, "message": str(exc)})
                except Exception as exc:
                    error_code = error_code or "tts_unavailable"
                    await self.events.broadcast({"type": "warning", "job_id": job_id, "message": str(exc)})

            timings["total_seconds"] = round(time.perf_counter() - started, 3)
            snapshot = self.metrics.snapshot()
            peak_memory = max(peak_memory, float(snapshot.get("memory_used_mb") or 0))
            self.history.add(
                InteractionRecord(
                    id=job_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    input_mode=input_mode,
                    transcript=transcript,
                    response=response,
                    model=model,
                    include_image=include_image,
                    timings=timings,
                    peak_memory_mb=peak_memory or None,
                    temperature_c=snapshot.get("temperature_c"),
                    error_code=error_code,
                )
            )
            self._jobs[job_id] = JobResult(job_id=job_id, done=True)
            await self._set_state(AssistantState.IDLE, active_job_id=None, metrics=snapshot, timings=timings)
            await self.events.broadcast({"type": "complete", "job_id": job_id})
        except Exception as exc:
            error_code = self._error_code(exc)
            timings["total_seconds"] = round(time.perf_counter() - started, 3)
            self._jobs[job_id] = JobResult(job_id=job_id, done=True, error=str(exc))
            await self._set_state(AssistantState.ERROR, error=str(exc), timings=timings)
            self.history.add(
                InteractionRecord(
                    id=job_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    input_mode=input_mode,
                    transcript=transcript,
                    response=response,
                    model=model,
                    include_image=include_image,
                    timings=timings,
                    peak_memory_mb=peak_memory or None,
                    temperature_c=self.metrics.temperature(),
                    error_code=error_code,
                )
            )
            if "ollama" in error_code:
                await self.ollama.unload(model)
            await self.events.broadcast({"type": "failed", "job_id": job_id, "message": str(exc)})
            await self._set_state(AssistantState.IDLE, active_job_id=None, error=str(exc))
        finally:
            if audio_path:
                audio_path.unlink(missing_ok=True)
            if image_path:
                image_path.unlink(missing_ok=True)
            self.media.cleanup()
            if lock_held and self._interaction_lock.locked():
                self._interaction_lock.release()

    async def stop_playback(self) -> None:
        await self.audio.stop_playback()

    async def shutdown(self) -> None:
        await self.audio.cancel_recording()
        await self.audio.stop_playback()
        if self._tasks:
            for task in self._tasks.values():
                task.cancel()
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    async def refresh_metrics(self) -> RuntimeStatus:
        await self._update(metrics=self.metrics.snapshot())
        return self.status

    async def _set_state(self, state: AssistantState, **changes: Any) -> None:
        self.status = self.status.model_copy(
            update={"state": state, "updated_at": datetime.now(timezone.utc).isoformat(), **changes}
        )
        await self.events.broadcast({"type": "status", "status": self.status.model_dump(mode="json")})

    async def _update(self, **changes: Any) -> None:
        await self._set_state(self.status.state, **changes)

    def _memory_used(self) -> float:
        return float(self.metrics.snapshot().get("memory_used_mb") or 0)

    @staticmethod
    def _ollama_timings(stats: dict[str, Any]) -> dict[str, float]:
        result: dict[str, float] = {}
        for key in ("total_duration", "load_duration", "eval_duration"):
            if stats.get(key) is not None:
                result[f"ollama_{key}_seconds"] = round(float(stats[key]) / 1_000_000_000, 3)
        count = stats.get("eval_count")
        duration = stats.get("eval_duration")
        if count and duration:
            result["tokens_per_second"] = round(float(count) / (float(duration) / 1_000_000_000), 3)
        return result

    @staticmethod
    def _error_code(exc: Exception) -> str:
        name = exc.__class__.__name__.lower()
        if "ollama" in name:
            return "ollama_error"
        if "asr" in name:
            return "asr_error"
        if "audio" in name:
            return "audio_error"
        return "interaction_error"
