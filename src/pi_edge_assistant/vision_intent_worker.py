from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--threshold", type=float)
    args = parser.parse_args()
    text = sys.stdin.read().strip()
    if not text:
        raise ValueError("vision intent input is empty")

    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, args.threads)
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(
        str(args.model_dir / "model.onnx"),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )

    tokenizer = Tokenizer.from_file(str(args.model_dir / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=128)
    encoded = tokenizer.encode("query: " + text)
    attention_mask = np.asarray([encoded.attention_mask], dtype=np.int64)
    inputs = {
        "input_ids": np.asarray([encoded.ids], dtype=np.int64),
        "attention_mask": attention_mask,
        "token_type_ids": np.asarray([encoded.type_ids], dtype=np.int64),
    }
    hidden = session.run(None, inputs)[0]
    pooled = (hidden * attention_mask[..., None]).sum(axis=1) / attention_mask.sum(axis=1, keepdims=True)
    pooled /= np.linalg.norm(pooled, axis=1, keepdims=True)

    head = np.load(args.model_dir / "vision_intent_head.npz")
    weight = head["weight"]
    if weight.shape != (pooled.shape[1],):
        raise ValueError(f"classification head has shape {weight.shape}, expected {(pooled.shape[1],)}")
    threshold = float(args.threshold if args.threshold is not None else head["capture_threshold"])
    logit = float(pooled[0] @ weight + float(head["bias"]))
    probability = float(1.0 / (1.0 + np.exp(-logit)))
    print(json.dumps({"capture": probability >= threshold, "probability": probability, "threshold": threshold}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
