from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path


class ASRError(RuntimeError):
    pass


class WhisperService:
    def __init__(self, cli_path: Path, model_path: Path) -> None:
        self.cli_path = cli_path
        self.model_path = model_path

    async def transcribe(self, audio_path: Path) -> tuple[str, float]:
        if not self.cli_path.exists():
            raise ASRError(f"whisper-cli not found: {self.cli_path}")
        if not self.model_path.exists():
            raise ASRError(f"Whisper model not found: {self.model_path}")
        output_prefix = audio_path.with_suffix("")
        process = await asyncio.create_subprocess_exec(
            str(self.cli_path),
            "-m",
            str(self.model_path),
            "-f",
            str(audio_path),
            "-oj",
            "-of",
            str(output_prefix),
            "-l",
            "auto",
            "-t",
            "4",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        json_path = output_prefix.with_suffix(".json")
        try:
            if process.returncode != 0:
                detail = stderr.decode(errors="replace").strip()
                raise ASRError(detail or "whisper-cli failed")
            text = self._parse_output(json_path, stdout.decode(errors="replace"))
            if not text:
                raise ASRError("no speech was recognized")
            return text, self._duration(audio_path)
        finally:
            json_path.unlink(missing_ok=True)

    @staticmethod
    def _parse_output(json_path: Path, stdout: str) -> str:
        if json_path.exists():
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            transcription = payload.get("transcription", [])
            if isinstance(transcription, list):
                return "".join(str(item.get("text", "")) for item in transcription).strip()
            if isinstance(payload.get("text"), str):
                return payload["text"].strip()
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        return " ".join(lines).strip()

    @staticmethod
    def _duration(audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as wav:
            return wav.getnframes() / wav.getframerate()
