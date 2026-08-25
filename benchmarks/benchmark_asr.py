#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
from pathlib import Path

from pi_edge_assistant.services.asr import WhisperService


def levenshtein(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for index, expected in enumerate(reference, start=1):
        current = [index]
        for other_index, actual in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other_index] + 1,
                    previous[other_index - 1] + (expected != actual),
                )
            )
        previous = current
    return previous[-1]


def units(text: str, language: str) -> list[str]:
    normalized = re.sub(r"[^\w\u3400-\u9fff]+", " ", text.casefold()).strip()
    if language == "zh":
        return [char for char in normalized if not char.isspace()]
    return normalized.split()


async def run(args: argparse.Namespace) -> int:
    manifest_path = args.manifest.resolve()
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results: list[dict] = []
    for model in args.models:
        service = WhisperService(args.whisper_cli, model)
        for row in rows:
            audio = (manifest_path.parent / row["audio"]).resolve()
            try:
                started = asyncio.get_running_loop().time()
                text, duration = await service.transcribe(audio)
                elapsed = asyncio.get_running_loop().time() - started
                ref_units = units(row["text"], row["language"])
                hyp_units = units(text, row["language"])
                error_rate = levenshtein(ref_units, hyp_units) / max(1, len(ref_units))
                normalized_text = text.casefold()
                slots = row.get("slots", [])
                slot_accuracy = sum(slot.casefold() in normalized_text for slot in slots) / max(1, len(slots)) if slots else None
                result = {
                    "model": str(model),
                    "audio": row["audio"],
                    "language": row["language"],
                    "reference": row["text"],
                    "hypothesis": text,
                    "error_rate": round(error_rate, 4),
                    "slot_accuracy": slot_accuracy,
                    "audio_seconds": round(duration, 3),
                    "asr_seconds": round(elapsed, 3),
                    "rtf": round(elapsed / duration, 4) if duration else None,
                }
            except Exception as exc:
                result = {"model": str(model), "audio": row["audio"], "error": str(exc)}
            results.append(result)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in results) + "\n", encoding="utf-8")
    for model in args.models:
        valid = [row for row in results if row.get("model") == str(model) and "error" not in row]
        if not valid:
            print(f"{model}: no valid results")
            continue
        print(
            f"{model}: median_error={statistics.median(row['error_rate'] for row in valid):.3f} "
            f"median_rtf={statistics.median(row['rtf'] for row in valid):.3f} samples={len(valid)}"
        )
    return 0 if all("error" not in row for row in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark multilingual whisper.cpp models")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--whisper-cli", type=Path, default=Path.home() / "whisper.cpp/build/bin/whisper-cli")
    parser.add_argument(
        "--models",
        type=Path,
        nargs="+",
        default=[
            Path.home() / "whisper.cpp/models/ggml-base-q5_0.bin",
            Path.home() / "whisper.cpp/models/ggml-small-q5_0.bin",
        ],
    )
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/asr.jsonl"))
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
