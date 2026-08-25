from __future__ import annotations

from pathlib import Path


class FakeAudio:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.recording_path: Path | None = None
        self.played: list[Path] = []

    async def start_recording(self) -> Path:
        self.recording_path = self.runtime_dir / "recording-fake.wav"
        self.recording_path.write_bytes(b"RIFF" + b"x" * 100)
        return self.recording_path

    async def stop_recording(self) -> Path:
        assert self.recording_path
        path = self.recording_path
        self.recording_path = None
        return path

    async def cancel_recording(self) -> None:
        if self.recording_path:
            self.recording_path.unlink(missing_ok=True)
        self.recording_path = None

    async def play(self, paths: list[Path]) -> None:
        self.played.extend(paths)

    async def stop_playback(self) -> None:
        return None


class FakeCamera:
    def __init__(self, runtime_dir: Path, fail: bool = False) -> None:
        self.runtime_dir = runtime_dir
        self.fail = fail
        self.calls = 0

    async def capture(self) -> Path:
        self.calls += 1
        if self.fail:
            raise RuntimeError("camera offline")
        path = self.runtime_dir / "capture-fake.jpg"
        path.write_bytes(b"jpeg")
        return path


class FakeASR:
    async def transcribe(self, _: Path) -> tuple[str, float]:
        return "看看摄像头", 2.0


class FakeOllama:
    default_model = "qwen3.5:2b"
    compare_model = "qwen3.5:4b"

    def __init__(self) -> None:
        self.calls = []

    async def chat(self, text, image_path, compare=False):
        self.calls.append((text, image_path, compare))
        return "本地回复", self.compare_model if compare else self.default_model, {"eval_count": 10, "eval_duration": 2_000_000_000}

    async def unload(self, model=None) -> None:
        return None


class FakeTTS:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir

    async def synthesize(self, text: str, job_id: str) -> list[Path]:
        path = self.runtime_dir / f"tts-{job_id}-fake.wav"
        path.write_bytes(b"RIFFfake")
        return [path]


class FakeMetrics:
    def snapshot(self):
        return {
            "cpu_percent": 10,
            "memory_used_mb": 1024,
            "memory_percent": 12.5,
            "swap_used_mb": 0,
            "swap_percent": 0,
            "disk_free_gb": 32,
            "temperature_c": 50,
        }

    def temperature(self):
        return 50
