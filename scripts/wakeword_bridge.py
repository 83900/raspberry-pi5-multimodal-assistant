#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import shlex
from pathlib import Path

import httpx


async def wait_for_keyword(command: str, keywords: list[str]) -> None:
    parts = shlex.split(command)
    if not parts:
        raise RuntimeError("wake-word command is empty")
    process = await asyncio.create_subprocess_exec(
        *parts,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    try:
        async for raw_line in process.stdout:
            line = raw_line.decode(errors="replace").strip()
            if line:
                print(f"[kws] {line}", flush=True)
            normalized = line.casefold()
            if any(keyword.casefold() in normalized for keyword in keywords):
                return
        raise RuntimeError(f"wake-word process exited with code {await process.wait()}")
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()


async def trigger_interaction(client: httpx.AsyncClient, seconds: float) -> None:
    response = await client.post("/api/recording/start", json={"include_image": False})
    response.raise_for_status()
    job_id = response.json()["job_id"]
    print(f"wake word accepted; recording job={job_id}", flush=True)
    await asyncio.sleep(seconds)
    response = await client.post("/api/recording/stop")
    response.raise_for_status()
    while True:
        job = (await client.get(f"/api/jobs/{job_id}")).json()
        if job["done"]:
            if job.get("error"):
                raise RuntimeError(job["error"])
            return
        await asyncio.sleep(0.5)


async def run(args: argparse.Namespace) -> None:
    token = args.token_file.read_text(encoding="utf-8").strip()
    async with httpx.AsyncClient(
        base_url=args.url,
        headers={"X-Access-Token": token},
        timeout=args.timeout,
    ) as client:
        while True:
            await wait_for_keyword(args.command, args.keyword)
            try:
                await trigger_interaction(client, args.record_seconds)
            except httpx.HTTPStatusError as exc:
                print(f"assistant rejected wake interaction: {exc.response.text}", flush=True)
                await asyncio.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge sherpa-onnx KWS output to the assistant API")
    parser.add_argument("--command", required=True, help="KWS command; it must print the detected phrase")
    parser.add_argument("--keyword", action="append", default=["小派", "hey pi"])
    parser.add_argument("--record-seconds", type=float, default=8)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--token-file", type=Path, default=Path.home() / ".local/share/pi-edge-assistant/access-token")
    parser.add_argument("--timeout", type=float, default=240)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
