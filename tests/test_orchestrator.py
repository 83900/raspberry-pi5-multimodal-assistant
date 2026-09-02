from pathlib import Path

import pytest

from pi_edge_assistant.database import HistoryStore
from pi_edge_assistant.events import EventHub
from pi_edge_assistant.models import AssistantState
from pi_edge_assistant.orchestrator import BusyError, Orchestrator
from pi_edge_assistant.services.media import MediaStore

from fakes import FakeASR, FakeAudio, FakeCamera, FakeMetrics, FakeOllama, FakeTTS, FakeVisionIntent


def make_orchestrator(tmp_path: Path, camera_fail: bool = False, vision_intent=None) -> Orchestrator:
    runtime = tmp_path / "run"
    runtime.mkdir(parents=True)
    return Orchestrator(
        audio=FakeAudio(runtime),
        camera=FakeCamera(runtime, camera_fail),
        asr=FakeASR(),
        ollama=FakeOllama(),
        tts=FakeTTS(runtime),
        metrics=FakeMetrics(),
        media=MediaStore(runtime, 600),
        history=HistoryStore(tmp_path / "history.db"),
        events=EventHub(),
        tts_enabled=True,
        vision_intent=vision_intent,
    )


@pytest.mark.asyncio
async def test_text_interaction_completes_and_persists(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    job_id = await orchestrator.submit_chat("你好", include_image=False, compare=False)
    result = await orchestrator.wait_for_job(job_id)
    assert result.done and result.error is None
    assert orchestrator.status.state == AssistantState.IDLE
    assert orchestrator.status.response == "本地回复"
    assert orchestrator.history.list()[0].transcript == "你好"
    assert orchestrator.camera.calls == 0


@pytest.mark.asyncio
async def test_voice_visual_trigger_captures_then_deletes_media(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    job_id = await orchestrator.start_recording(include_image=False)
    assert orchestrator.status.state == AssistantState.RECORDING
    assert await orchestrator.stop_recording() == job_id
    await orchestrator.wait_for_job(job_id)
    assert orchestrator.camera.calls == 1
    assert orchestrator.ollama.calls[0][1] is not None
    assert not list((tmp_path / "run").glob("recording-*.wav"))
    assert not list((tmp_path / "run").glob("capture-*.jpg"))


@pytest.mark.asyncio
async def test_camera_failure_degrades_to_text(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path, camera_fail=True)
    job_id = await orchestrator.submit_chat("看看画面", include_image=False, compare=False)
    result = await orchestrator.wait_for_job(job_id)
    assert result.error is None
    record = orchestrator.history.list()[0]
    assert record.response == "本地回复"
    assert record.error_code == "camera_unavailable"
    assert orchestrator.ollama.calls[0][1] is None


@pytest.mark.asyncio
async def test_classifier_can_trigger_camera_without_keyword(tmp_path: Path) -> None:
    classifier = FakeVisionIntent(capture=True, probability=0.6864)
    orchestrator = make_orchestrator(tmp_path, vision_intent=classifier)
    job_id = await orchestrator.submit_chat("我手里拿的是什么？", include_image=False, compare=False)
    await orchestrator.wait_for_job(job_id)

    assert classifier.calls == ["我手里拿的是什么？"]
    assert orchestrator.camera.calls == 1
    assert orchestrator.history.list()[0].include_image is True
    assert orchestrator.status.timings["vision_intent_probability"] == 0.6864


@pytest.mark.asyncio
async def test_explicit_checkbox_skips_classifier(tmp_path: Path) -> None:
    classifier = FakeVisionIntent(capture=False, probability=0.1)
    orchestrator = make_orchestrator(tmp_path, vision_intent=classifier)
    job_id = await orchestrator.submit_chat("普通问题", include_image=True, compare=False)
    await orchestrator.wait_for_job(job_id)

    assert classifier.calls == []
    assert orchestrator.camera.calls == 1


@pytest.mark.asyncio
async def test_busy_request_is_rejected(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    await orchestrator.start_recording(include_image=False)
    with pytest.raises(BusyError):
        await orchestrator.submit_chat("second", False, False)
    await orchestrator.audio.cancel_recording()
    orchestrator._interaction_lock.release()
