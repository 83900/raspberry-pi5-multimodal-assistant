#!/usr/bin/env python3
"""Download an Ollama registry model bundle without installing Ollama.

The resulting blobs/manifests tree can be copied into Ollama's models directory.
Only Python's standard library is required, so this is suitable for a Mac used as
a download relay for a Raspberry Pi with an unreliable network connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path


REGISTRY = "https://registry.ollama.ai"


def parse_model(value: str) -> tuple[str, str, str]:
    name, separator, tag = value.partition(":")
    tag = tag if separator else "latest"
    if not name or not tag or name.startswith("/") or ".." in name:
        raise ValueError(f"invalid model name: {value}")
    if "/" in name:
        namespace, repository = name.rsplit("/", 1)
    else:
        namespace, repository = "library", name
    return namespace, repository, tag


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def download_blob(url: str, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=120)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and partial.exists():
            partial.replace(destination)
            return
        raise
    mode = "ab" if offset and response.status == 206 else "wb"
    with response, partial.open(mode) as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    partial.replace(destination)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", help="model and tag, for example qwen3.5:4b")
    parser.add_argument("output", type=Path, help="output bundle directory")
    args = parser.parse_args()

    namespace, repository, tag = parse_model(args.model)
    manifest_url = f"{REGISTRY}/v2/{namespace}/{repository}/manifests/{tag}"
    manifest_bytes = request_bytes(manifest_url)
    manifest = json.loads(manifest_bytes)
    descriptors = [manifest["config"], *manifest.get("layers", [])]

    blobs_dir = args.output / "blobs"
    manifest_path = args.output / "manifests" / "registry.ollama.ai" / namespace / repository / tag
    blobs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    for index, descriptor in enumerate(descriptors, start=1):
        digest = str(descriptor["digest"])
        algorithm, value = digest.split(":", 1)
        if algorithm != "sha256":
            raise RuntimeError(f"unsupported digest: {digest}")
        destination = blobs_dir / f"sha256-{value}"
        if destination.exists() and sha256(destination) == value:
            print(f"[{index}/{len(descriptors)}] cached {destination.name}")
            continue
        print(f"[{index}/{len(descriptors)}] downloading {digest}")
        download_blob(f"{REGISTRY}/v2/{namespace}/{repository}/blobs/{digest}", destination)
        if sha256(destination) != value:
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"checksum mismatch: {digest}")

    manifest_path.write_bytes(manifest_bytes)
    print(f"Bundle ready: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
