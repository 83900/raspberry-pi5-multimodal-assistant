#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from pi_edge_assistant.services.ollama import OllamaService


async def run(args: argparse.Namespace) -> int:
    manifest = args.manifest.resolve()
    cases = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    results: list[dict] = []
    for model in args.models:
        service = OllamaService(args.url, model, model, args.context, args.max_tokens, args.timeout)
        await service.unload(model)
        for case in cases:
            image = (manifest.parent / case["image"]).resolve() if case.get("image") else None
            started = time.perf_counter()
            try:
                response, _, stats = await service.chat(case["text"], image)
                result = {
                    "id": case["id"],
                    "model": model,
                    "language": case.get("language"),
                    "has_image": bool(image),
                    "prompt": case["text"],
                    "response": response,
                    "wall_seconds": round(time.perf_counter() - started, 3),
                    "stats": stats,
                    "human_correctness_0_2": None,
                    "human_grounding_0_2": None,
                    "human_instruction_0_2": None,
                    "human_hallucination_0_2": None,
                }
            except Exception as exc:
                result = {"id": case["id"], "model": model, "error": str(exc)}
            results.append(result)
        await service.unload(model)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in results) + "\n", encoding="utf-8")
    for model in args.models:
        valid = [row for row in results if row.get("model") == model and "wall_seconds" in row]
        if valid:
            print(f"{model}: median_wall={statistics.median(row['wall_seconds'] for row in valid):.2f}s samples={len(valid)}")
    return 0 if all("error" not in row for row in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Ollama text and image cases")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--models", nargs="+", default=["qwen3.5:2b", "qwen3.5:4b"])
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--max-tokens", type=int, default=192)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/ollama.jsonl"))
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
