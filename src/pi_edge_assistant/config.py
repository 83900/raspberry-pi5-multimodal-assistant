from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    data_dir: Path = Path("data")
    runtime_dir: Path = Path("/run/user/1000/pi-edge-assistant")
    host: str = "0.0.0.0"
    port: int = 8080
    access_token: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:2b"
    ollama_compare_model: str = "qwen3.5:4b"
    ollama_context: int = 4096
    ollama_max_tokens: int = 192
    ollama_timeout_seconds: float = 180.0
    whisper_cli: Path = Path.home() / "whisper.cpp/build/bin/whisper-cli"
    whisper_model: Path = Path.home() / "whisper.cpp/models/ggml-base-q5_0.bin"
    audio_device: str = "default"
    playback_device: str = "default"
    zh_voice: Path | None = None
    en_voice: Path | None = None
    tts_enabled: bool = True
    camera_width: int = 640
    camera_height: int = 480
    media_ttl_seconds: int = 600

    @classmethod
    def from_env(cls) -> "Settings":
        runtime_default = Path(os.getenv("XDG_RUNTIME_DIR", "/tmp")) / "pi-edge-assistant"
        return cls(
            data_dir=Path(os.getenv("EDGE_DATA_DIR", "data")),
            runtime_dir=Path(os.getenv("EDGE_RUNTIME_DIR", str(runtime_default))),
            host=os.getenv("EDGE_HOST", "0.0.0.0"),
            port=int(os.getenv("EDGE_PORT", "8080")),
            access_token=os.getenv("EDGE_ACCESS_TOKEN") or None,
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3.5:2b"),
            ollama_compare_model=os.getenv("OLLAMA_COMPARE_MODEL", "qwen3.5:4b"),
            ollama_context=int(os.getenv("OLLAMA_CONTEXT", "4096")),
            ollama_max_tokens=int(os.getenv("OLLAMA_MAX_TOKENS", "192")),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180")),
            whisper_cli=Path(os.getenv("WHISPER_CLI", str(Path.home() / "whisper.cpp/build/bin/whisper-cli"))),
            whisper_model=Path(os.getenv("WHISPER_MODEL", str(Path.home() / "whisper.cpp/models/ggml-base-q5_0.bin"))),
            audio_device=os.getenv("AUDIO_CAPTURE_DEVICE", "default"),
            playback_device=os.getenv("AUDIO_PLAYBACK_DEVICE", "default"),
            zh_voice=Path(value) if (value := os.getenv("PIPER_ZH_VOICE")) else None,
            en_voice=Path(value) if (value := os.getenv("PIPER_EN_VOICE")) else None,
            tts_enabled=_env_bool("TTS_ENABLED", True),
            camera_width=int(os.getenv("CAMERA_WIDTH", "640")),
            camera_height=int(os.getenv("CAMERA_HEIGHT", "480")),
            media_ttl_seconds=int(os.getenv("MEDIA_TTL_SECONDS", "600")),
        )

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.runtime_dir.chmod(0o700)
        except OSError:
            pass

    def resolve_access_token(self) -> str:
        if self.access_token:
            return self.access_token
        self.prepare()
        token_file = self.data_dir / "access-token"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
            if token:
                self.access_token = token
                return token
        token = secrets.token_urlsafe(24)
        token_file.write_text(token + "\n", encoding="utf-8")
        token_file.chmod(0o600)
        self.access_token = token
        return token
