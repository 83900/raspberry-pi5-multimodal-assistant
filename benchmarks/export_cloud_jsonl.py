#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export provider-neutral cloud comparison JSONL")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/cloud-export.jsonl"))
    args = parser.parse_args()
    source = args.manifest.resolve()
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        rows.append(
            {
                "id": case["id"],
                "messages": [{"role": "user", "content": case["text"]}],
                "local_image_path": str((source.parent / case["image"]).resolve()) if case.get("image") else None,
                "cloud_response": None,
                "human_score": None,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
