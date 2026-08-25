from __future__ import annotations

import asyncio
import signal
import uuid
from pathlib import Path


class AudioError(RuntimeError):
    pass


class AudioService:
    def __init__(self, runtime_dir: Path, capture_device: str, playback_device: str) -> None:
        self.runtime_dir = runtime_dir
        self.capture_device = capture_device
        self.playback_device = playback_device
        self._capture_process: asyncio.subprocess.Process | None = None
        self._capture_path: Path | None = None
        self._playback_process: asyncio.subprocess.Process | None = None

    async def start_recording(self) -> Path:
        if self._capture_process is not None:
            raise AudioError("recording is already active")
        path = self.runtime_dir / f"recording-{uuid.uuid4().hex}.wav"
        try:
            process = await asyncio.create_subprocess_exec(
                "arecord",
                "-q",
                "-D",
                self.capture_device,
                "-f",
                "S16_LE",
                "-r",
                "16000",
                "-c",
                "1",
                str(path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise AudioError("arecord is not installed") from exc
        await asyncio.sleep(0.1)
        if process.returncode is not None:
            stderr = (await process.stderr.read()).decode(errors="replace")
            raise AudioError(stderr.strip() or "unable to start microphone capture")
        self._capture_process = process
        self._capture_path = path
        return path

    async def stop_recording(self) -> Path:
        process = self._capture_process
        path = self._capture_path
        if process is None or path is None:
            raise AudioError("recording is not active")
        process.send_signal(signal.SIGINT)
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
        finally:
            self._capture_process = None
            self._capture_path = None
        if not path.exists() or path.stat().st_size <= 44:
            path.unlink(missing_ok=True)
            raise AudioError("microphone produced an empty recording")
        return path

    async def cancel_recording(self) -> None:
        if self._capture_process is not None:
            self._capture_process.kill()
            await self._capture_process.wait()
        self._capture_process = None
        if self._capture_path:
            self._capture_path.unlink(missing_ok=True)
        self._capture_path = None

    async def play(self, paths: list[Path]) -> None:
        for path in paths:
            try:
                self._playback_process = await asyncio.create_subprocess_exec(
                    "aplay",
                    "-q",
                    "-D",
                    self.playback_device,
                    str(path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise AudioError("aplay is not installed") from exc
            _, stderr = await self._playback_process.communicate()
            if self._playback_process.returncode != 0:
                raise AudioError(stderr.decode(errors="replace").strip() or "audio playback failed")
        self._playback_process = None

    async def stop_playback(self) -> None:
        if self._playback_process and self._playback_process.returncode is None:
            self._playback_process.terminate()
            try:
                await asyncio.wait_for(self._playback_process.wait(), timeout=2)
            except TimeoutError:
                self._playback_process.kill()
                await self._playback_process.wait()
        self._playback_process = None
