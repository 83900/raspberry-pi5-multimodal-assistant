from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AssistantState(StrEnum):
    IDLE = "IDLE"
    RECORDING = "RECORDING"
    TRANSCRIBING = "TRANSCRIBING"
    CAPTURING = "CAPTURING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8_000)
    include_image: bool = False
    compare_model: bool = False


class RecordingStartRequest(BaseModel):
    include_image: bool = False


class AcceptedJob(BaseModel):
    job_id: str
    status: str = "accepted"


class InteractionRecord(BaseModel):
    id: str
    created_at: str
    input_mode: str
    transcript: str
    response: str
    model: str
    include_image: bool
    timings: dict[str, float]
    peak_memory_mb: float | None = None
    temperature_c: float | None = None
    error_code: str | None = None


class RuntimeStatus(BaseModel):
    state: AssistantState = AssistantState.IDLE
    active_job_id: str | None = None
    transcript: str = ""
    response: str = ""
    model: str = ""
    include_image: bool = False
    timings: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    audio_urls: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JobResult(BaseModel):
    job_id: str
    done: bool = False
    error: str | None = None
