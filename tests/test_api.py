from pathlib import Path

from fastapi.testclient import TestClient

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
