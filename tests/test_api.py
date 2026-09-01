from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pi_edge_assistant.app import create_app
from pi_edge_assistant.config import Settings

from test_orchestrator import make_orchestrator


def test_api_requires_token_and_runs_chat(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        runtime_dir=tmp_path / "runtime",
        access_token="test-token",
        tts_enabled=True,
    )
    settings.runtime_dir.mkdir()
    orchestrator = make_orchestrator(tmp_path / "orchestrator")
    app = create_app(settings, orchestrator)
    with TestClient(app) as client:
        assert client.get("/api/status").status_code == 401
        headers = {"X-Access-Token": "test-token"}
        response = client.post("/api/chat", headers=headers, json={"text": "hello", "include_image": False})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
            if job["done"]:
                break
        assert job == {"job_id": job_id, "done": True, "error": None}
        history = client.get("/api/history", headers=headers).json()
        assert history[0]["response"] == "本地回复"
        with client.websocket_connect("/api/events") as websocket:
            websocket.send_json({"token": "test-token"})
            event = websocket.receive_json()
            assert event["type"] == "status"


def test_health_does_not_expose_runtime_data(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", runtime_dir=tmp_path / "runtime", access_token="main-token")
    settings.runtime_dir.mkdir()
    app = create_app(settings, make_orchestrator(tmp_path / "orchestrator"))
    with TestClient(app, client=("192.168.1.50", 50000)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_display_session_is_loopback_only(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", runtime_dir=tmp_path / "runtime", access_token="main-token")
    settings.runtime_dir.mkdir()
    app = create_app(settings, make_orchestrator(tmp_path / "orchestrator"))

    with TestClient(app, client=("127.0.0.1", 50000)) as local_client:
        response = local_client.post("/api/display/session")
        assert response.status_code == 200
        display_token = response.json()["token"]
        headers = {"X-Access-Token": display_token}
        assert local_client.get("/api/status", headers=headers).status_code == 200
        with local_client.websocket_connect("/api/events") as websocket:
            websocket.send_json({"token": display_token})
            assert websocket.receive_json()["type"] == "status"

    with TestClient(app, client=("192.168.1.50", 50000)) as remote_client:
        assert remote_client.post("/api/display/session").status_code == 403
        assert remote_client.get("/api/status", headers=headers).status_code == 401
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with remote_client.websocket_connect("/api/events") as websocket:
                websocket.send_json({"token": display_token})
                websocket.receive_json()
        assert exc_info.value.code == 1008
        assert remote_client.get("/api/status", headers={"X-Access-Token": "main-token"}).status_code == 200
