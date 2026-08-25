from __future__ import annotations

import time
from pathlib import Path


class MediaStore:
    def __init__(self, runtime_dir: Path, ttl_seconds: int) -> None:
        self.runtime_dir = runtime_dir
        self.ttl_seconds = ttl_seconds

    def audio_for_job(self, job_id: str) -> list[Path]:
        return sorted(self.runtime_dir.glob(f"tts-{job_id}-*.wav"))

    def get_audio(self, job_id: str, name: str) -> Path | None:
        if Path(name).name != name or not name.startswith(f"tts-{job_id}-") or not name.endswith(".wav"):
            return None
        path = self.runtime_dir / name
        return path if path.is_file() else None

    def cleanup(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for pattern in ("tts-*.wav", "recording-*.wav", "capture-*.jpg"):
            for path in self.runtime_dir.glob(pattern):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
