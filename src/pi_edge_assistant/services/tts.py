from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path


class TTSError(RuntimeError):
    pass


_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def split_by_language(text: str) -> list[tuple[str, str]]:
    if not text.strip():
        return []
    pending = ""
    current_language: str | None = None
    current = ""
    result: list[tuple[str, str]] = []
    for char in text.strip():
        language = "zh" if _CJK_RE.match(char) else "en" if _LATIN_RE.match(char) else None
        if language is None:
            if current_language is None:
                pending += char
            else:
                current += char
            continue
        if current_language is None:
            current_language = language
            current = pending + char
            pending = ""
            continue
        if language != current_language:
            result.append((current_language, current.strip()))
            current_language = language
            current = char
        else:
            current += char
    if current_language is not None and current.strip():
        result.append((current_language, current.strip()))
    elif pending and result:
        language, chunk = result[-1]
        result[-1] = (language, chunk + pending)
    return result


class PiperService:
    def __init__(self, runtime_dir: Path, zh_voice: Path | None, en_voice: Path | None) -> None:
        self.runtime_dir = runtime_dir
        self.voice_paths = {"zh": zh_voice, "en": en_voice}
        self._voices: dict[str, object] = {}

    async def synthesize(self, text: str, job_id: str) -> list[Path]:
        return await asyncio.to_thread(self._synthesize_sync, text, job_id)

    def _synthesize_sync(self, text: str, job_id: str) -> list[Path]:
        try:
            from piper.voice import PiperVoice
        except ImportError as exc:
            raise TTSError("piper-tts is not installed") from exc
        output: list[Path] = []
        for language, chunk in split_by_language(text):
            voice_path = self.voice_paths.get(language)
            if voice_path is None or not voice_path.exists():
                raise TTSError(f"Piper {language} voice is not configured")
            voice = self._voices.get(language)
            if voice is None:
                voice = PiperVoice.load(str(voice_path))
                self._voices[language] = voice
            path = self.runtime_dir / f"tts-{job_id}-{uuid.uuid4().hex}.wav"
            import wave

            with wave.open(str(path), "wb") as wav_file:
                voice.synthesize_wav(chunk, wav_file)
            output.append(path)
        return output
