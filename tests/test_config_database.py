from pathlib import Path

from pi_edge_assistant.config import Settings
from pi_edge_assistant.database import HistoryStore
from pi_edge_assistant.models import InteractionRecord


def test_access_token_is_created_once(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", runtime_dir=tmp_path / "run")
    first = settings.resolve_access_token()
    second = Settings(data_dir=settings.data_dir, runtime_dir=settings.runtime_dir).resolve_access_token()
    assert first == second
    assert len(first) >= 24
    assert (settings.data_dir / "access-token").read_text().strip() == first


def test_history_round_trip_and_clear(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "assistant.db")
    record = InteractionRecord(
        id="job-1",
        created_at="2026-08-21T00:00:00+00:00",
        input_mode="text",
        transcript="你好",
        response="你好！",
        model="qwen3.5:2b",
        include_image=False,
        timings={"total_seconds": 1.2},
        peak_memory_mb=1234.0,
        temperature_c=52.0,
    )
    store.add(record)
    assert store.list() == [record]
    store.clear()
    assert store.list() == []
    store.close()
