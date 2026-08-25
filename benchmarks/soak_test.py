#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx


PROMPTS = (
    "用一句话说明当前运行模式。",
    "What can you do locally? Answer briefly.",
    "请用英文列出两个边缘计算的优点。",
    "Explain in Chinese why local inference improves privacy.",
    "把这句话翻译为英文：摄像头只在需要时开启。",
    "Translate into Chinese: Raw media is deleted after each interaction.",
)


async def run(args: argparse.Namespace) -> int:
    token = args.token_file.read_text(encoding="utf-8").strip()
    headers = {"X-Access-Token": token}
    records = []
    async with httpx.AsyncClient(base_url=args.url, headers=headers, timeout=args.timeout) as client:
        for index in range(args.rounds):
            started = time.perf_counter()
            response = await client.post("/api/chat", json={"text": PROMPTS[index % len(PROMPTS)], "include_image": False})
            response.raise_for_status()
            job_id = response.json()["job_id"]
            error = None
            while True:
                await asyncio.sleep(0.5)
                job = (await client.get(f"/api/jobs/{job_id}")).json()
                if job["done"]:
                    error = job.get("error")
                    break
            status = (await client.get("/api/status")).json()
            records.append(
                {
                    "round": index + 1,
                    "job_id": job_id,
                    "seconds": round(time.perf_counter() - started, 3),
                    "error": error,
                    "memory_used_mb": status["metrics"].get("memory_used_mb"),
                    "swap_used_mb": status["metrics"].get("swap_used_mb"),
                    "temperature_c": status["metrics"].get("temperature_c"),
                }
            )
            print(json.dumps(records[-1], ensure_ascii=False))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    successes = [row for row in records if not row["error"]]
    success_rate = len(successes) / len(records)
    print(f"success_rate={success_rate:.1%} median_seconds={statistics.median(row['seconds'] for row in successes):.2f}")
    return 0 if success_rate >= 0.95 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a sequential 30-turn assistant soak test")
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--token-file", type=Path, default=Path.home() / ".local/share/pi-edge-assistant/access-token")
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/soak.json"))
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
