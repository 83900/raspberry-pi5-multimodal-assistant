import struct
import wave
from pathlib import Path

from pi_edge_assistant.services.asr import WhisperService
from pi_edge_assistant.services.audio import AudioService


def test_finalize_wav_replaces_streaming_length_placeholders(tmp_path: Path) -> None:
    path = tmp_path / "recording.wav"
    pcm = b"\x00\x00" * 1600
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        0x7FFFFFFF,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        16000,
        32000,
        2,
        16,
        b"data",
        0x7FFFFFFF,
    )
    path.write_bytes(header + pcm)

    AudioService._finalize_wav(path)

    with path.open("rb") as wav_file:
        assert wav_file.read(4) == b"RIFF"
        assert struct.unpack("<I", wav_file.read(4))[0] == path.stat().st_size - 8
        wav_file.seek(40)
        assert struct.unpack("<I", wav_file.read(4))[0] == len(pcm)
    with wave.open(str(path), "rb") as wav:
        assert wav.getnframes() == 1600
        assert wav.getframerate() == 16000


def test_whisper_error_omits_model_initialization_log() -> None:
    stderr = """whisper_init_from_file_with_params_no_state: loading model
whisper_model_load: loading model
error: failed to decode audio
"""
    assert WhisperService._failure_detail(stderr) == "error: failed to decode audio"


def test_whisper_blank_audio_marker_is_not_a_transcript(tmp_path: Path) -> None:
    json_path = tmp_path / "recording.json"
    json_path.write_text('{"transcription": [{"text": "[BLANK_AUDIO]"}]}', encoding="utf-8")
    assert WhisperService._parse_output(json_path, "") == ""
