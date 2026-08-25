from __future__ import annotations

import logging
import secrets
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .database import HistoryStore
from .events import EventHub
from .models import AcceptedJob, ChatRequest, RecordingStartRequest
from .orchestrator import BusyError, Orchestrator
from .services.asr import WhisperService
from .services.audio import AudioService
from .services.camera import CameraService
from .services.media import MediaStore
from .services.metrics import MetricsService
from .services.ollama import OllamaService
from .services.tts import PiperService

logger = logging.getLogger(__name__)


def build_orchestrator(settings: Settings) -> Orchestrator:
    settings.prepare()
    return Orchestrator(
        audio=AudioService(settings.runtime_dir, settings.audio_device, settings.playback_device),
        camera=CameraService(settings.runtime_dir, settings.camera_width, settings.camera_height),
        asr=WhisperService(settings.whisper_cli, settings.whisper_model),
        ollama=OllamaService(
            settings.ollama_url,
            settings.ollama_model,
            settings.ollama_compare_model,
            settings.ollama_context,
            settings.ollama_max_tokens,
            settings.ollama_timeout_seconds,
        ),
        tts=PiperService(settings.runtime_dir, settings.zh_voice, settings.en_voice),
        metrics=MetricsService(),
        media=MediaStore(settings.runtime_dir, settings.media_ttl_seconds),
        history=HistoryStore(settings.data_dir / "assistant.db"),
        events=EventHub(),
        tts_enabled=settings.tts_enabled,
    )


def create_app(settings: Settings | None = None, orchestrator: Orchestrator | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.prepare()
    access_token = settings.resolve_access_token()
    orchestrator = orchestrator or build_orchestrator(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info("Access token file: %s", settings.data_dir / "access-token")
        yield
        await orchestrator.shutdown()
        orchestrator.history.close()

    app = FastAPI(title="Pi Edge Assistant", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.orchestrator = orchestrator

    def authorize(x_access_token: str | None = Header(default=None)) -> None:
        if not x_access_token or not secrets.compare_digest(x_access_token, access_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token")

    @app.get("/api/status")
    async def get_status(x_access_token: str | None = Header(default=None)):
        authorize(x_access_token)
        return await orchestrator.refresh_metrics()

    @app.get("/api/history")
    async def get_history(
        limit: int = Query(default=100, ge=1, le=500),
        x_access_token: str | None = Header(default=None),
    ):
        authorize(x_access_token)
        return orchestrator.history.list(limit)

    @app.delete("/api/history", status_code=status.HTTP_204_NO_CONTENT)
    async def clear_history(x_access_token: str | None = Header(default=None)) -> None:
        authorize(x_access_token)
        orchestrator.history.clear()

    @app.post("/api/recording/start", response_model=AcceptedJob, status_code=status.HTTP_202_ACCEPTED)
    async def start_recording(
        request: RecordingStartRequest,
        x_access_token: str | None = Header(default=None),
    ) -> AcceptedJob:
        authorize(x_access_token)
        try:
            job_id = await orchestrator.start_recording(request.include_image)
        except BusyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return AcceptedJob(job_id=job_id)

    @app.post("/api/recording/stop", response_model=AcceptedJob, status_code=status.HTTP_202_ACCEPTED)
    async def stop_recording(x_access_token: str | None = Header(default=None)) -> AcceptedJob:
        authorize(x_access_token)
        try:
            job_id = await orchestrator.stop_recording()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return AcceptedJob(job_id=job_id)

    @app.post("/api/chat", response_model=AcceptedJob, status_code=status.HTTP_202_ACCEPTED)
    async def chat(request: ChatRequest, x_access_token: str | None = Header(default=None)) -> AcceptedJob:
        authorize(x_access_token)
        try:
            job_id = await orchestrator.submit_chat(request.text, request.include_image, request.compare_model)
        except BusyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return AcceptedJob(job_id=job_id)

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str, x_access_token: str | None = Header(default=None)):
        authorize(x_access_token)
        result = orchestrator.job(job_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        return result

    @app.post("/api/playback/stop", status_code=status.HTTP_204_NO_CONTENT)
    async def stop_playback(x_access_token: str | None = Header(default=None)) -> None:
        authorize(x_access_token)
        await orchestrator.stop_playback()

    @app.get("/api/audio/{job_id}/{name}")
    async def get_audio(job_id: str, name: str, x_access_token: str | None = Header(default=None)):
        authorize(x_access_token)
        path = orchestrator.media.get_audio(job_id, name)
        if path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audio not found or expired")
        return FileResponse(path, media_type="audio/wav", filename=name)

    @app.websocket("/api/events")
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            auth = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        except Exception:
            await websocket.close(code=1008)
            return
        supplied_token = str(auth.get("token", "")) if isinstance(auth, dict) else ""
        if not supplied_token or not secrets.compare_digest(supplied_token, access_token):
            await websocket.close(code=1008)
            return
        await orchestrator.events.connect(websocket, accept=False)
        await websocket.send_json({"type": "status", "status": orchestrator.status.model_dump(mode="json")})
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await orchestrator.events.disconnect(websocket)

    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
