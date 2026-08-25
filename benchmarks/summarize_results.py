#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def value(values: list[float]) -> str:
    return f"{statistics.median(values):.3f}" if values else "n/a"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Raspberry Pi acceptance report")
    parser.add_argument("--asr", type=Path, default=Path("benchmarks/results/asr.jsonl"))
    parser.add_argument("--ollama", type=Path, default=Path("benchmarks/results/ollama.jsonl"))
    parser.add_argument("--soak", type=Path, default=Path("benchmarks/results/soak.json"))
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/REPORT.md"))
    args = parser.parse_args()

    asr = read_jsonl(args.asr)
    ollama = read_jsonl(args.ollama)
    soak = json.loads(args.soak.read_text(encoding="utf-8")) if args.soak.exists() else []
    lines = [
        "# Raspberry Pi 5 Edge Assistant 验收报告",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## ASR",
        "",
        "| 模型 | 样本 | 中位错误率 | 中位 RTF | RTF≤1 |",
        "|---|---:|---:|---:|:---:|",
    ]
    for model in sorted({row.get("model") for row in asr if row.get("model")}):
        rows = [row for row in asr if row.get("model") == model and "error" not in row]
        median_rtf = statistics.median([row["rtf"] for row in rows]) if rows else None
        lines.append(
            f"| `{Path(model).name}` | {len(rows)} | {value([row['error_rate'] for row in rows])} | "
            f"{value([row['rtf'] for row in rows])} | {'✅' if median_rtf is not None and median_rtf <= 1 else '❌'} |"
        )

    lines += [
        "",
        "## Ollama",
        "",
        "| 模型 | 样本 | 成功 | 中位总耗时（秒） | 中位生成速度（token/s） |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in sorted({row.get("model") for row in ollama if row.get("model")}):
        rows = [row for row in ollama if row.get("model") == model]
        valid = [row for row in rows if "error" not in row]
        speeds = []
        for row in valid:
            stats = row.get("stats", {})
            if stats.get("eval_count") and stats.get("eval_duration"):
                speeds.append(stats["eval_count"] / (stats["eval_duration"] / 1_000_000_000))
        lines.append(
            f"| `{model}` | {len(rows)} | {len(valid)} | {value([row['wall_seconds'] for row in valid])} | {value(speeds)} |"
        )

    successes = [row for row in soak if not row.get("error")]
    success_rate = len(successes) / len(soak) if soak else 0
    max_memory = max((row.get("memory_used_mb") or 0 for row in soak), default=0)
    max_swap = max((row.get("swap_used_mb") or 0 for row in soak), default=0)
    max_temp = max((row.get("temperature_c") or 0 for row in soak), default=0)
    lines += [
        "",
        "## 30 轮稳定性",
        "",
        f"- 成功率：{success_rate:.1%}（目标 ≥95%）",
        f"- 峰值系统内存：{max_memory:.1f} MB（目标 ≤6656 MB）",
        f"- 峰值 swap：{max_swap:.1f} MB",
        f"- 峰值温度：{max_temp:.1f} °C（目标 <80 °C）",
        "",
        "## 判定与升级建议",
        "",
    ]
    if not soak:
        lines.append("- 尚未运行稳定性测试，不能做硬件采购判断。")
    else:
        lines.append(f"- 稳定性：{'通过' if success_rate >= .95 and max_memory <= 6656 else '未通过'}。")
        if max_temp >= 80:
            lines.append("- 温度达到 80°C：先检查官方电源和主动散热，不先购买 AI 加速器。")
        if max_swap > 100:
            lines.append("- 出现明显 swap：缩短上下文/切回 2B；若模型载入和存储也慢，再评估 NVMe。")
        if success_rate >= .95 and max_temp < 80 and max_memory <= 6656 and max_swap <= 100:
            lines.append("- 当前硬件满足第一版目标，暂不建议采购升级。")
    if args.audit and args.audit.exists():
        lines += ["", "## 审计附件", "", f"完整审计：`{args.audit}`"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
