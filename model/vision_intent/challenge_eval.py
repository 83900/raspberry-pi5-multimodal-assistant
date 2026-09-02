import json
from pathlib import Path

import numpy as np

from sentence_transformers import SentenceTransformer
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
)


MODEL_NAME = "intfloat/multilingual-e5-small"

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent

DATA_PATH = ROOT / "data" / "challenge_test.jsonl"

HEAD_PATH = (
    REPO_ROOT
    / "artifacts"
    / "vision_intent"
    / "vision_intent_head.npz"
)


def load_jsonl(path):
    rows = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            line = line.strip()

            if line:
                rows.append(
                    json.loads(line)
                )

    return rows


# -------------------------
# Load challenge set
# -------------------------

rows = load_jsonl(DATA_PATH)

print(
    f"challenge samples: {len(rows)}"
)

labels = np.array([
    row["label"]
    for row in rows
])


# -------------------------
# Load E5
# -------------------------

print("Loading E5...")

encoder = SentenceTransformer(
    MODEL_NAME
)

texts = [
    "query: " + row["text"].strip()
    for row in rows
]

print(
    "Encoding challenge set..."
)

embeddings = encoder.encode(
    texts,
    batch_size=32,
    normalize_embeddings=True,
    show_progress_bar=True,
)


# -------------------------
# Load trained LR head
# -------------------------

data = np.load(HEAD_PATH)

weight = data["weight"]
bias = float(data["bias"])

capture_threshold = float(
    data["capture_threshold"]
)

ask_threshold = float(
    data["ask_threshold"]
)

print(
    "capture threshold:",
    capture_threshold,
)

print(
    "ask threshold:",
    ask_threshold,
)


# -------------------------
# Manual Logistic Regression
# -------------------------

logits = (
    embeddings @ weight
    + bias
)

probabilities = (
    1.0
    /
    (
        1.0
        + np.exp(-logits)
    )
)

predictions = (
    probabilities
    >= capture_threshold
).astype(int)


# -------------------------
# Overall metrics
# -------------------------

print("\n=== CLASSIFICATION REPORT ===")

print(
    classification_report(
        labels,
        predictions,
        digits=4,
    )
)

print(
    "=== CONFUSION MATRIX ==="
)

print(
    confusion_matrix(
        labels,
        predictions,
    )
)


# -------------------------
# Per-language metrics
# -------------------------

languages = sorted(
    set(
        row["lang"]
        for row in rows
    )
)

print(
    "\n=== BY LANGUAGE ==="
)

for lang in languages:

    indexes = [
        i
        for i, row
        in enumerate(rows)
        if row["lang"] == lang
    ]

    y_true = labels[indexes]
    y_pred = predictions[indexes]

    correct = (
        y_true == y_pred
    ).sum()

    accuracy = (
        correct / len(indexes)
    )

    print(
        f"{lang:>5}: "
        f"{correct}/{len(indexes)} "
        f"accuracy={accuracy:.4f}"
    )


# -------------------------
# Wrong predictions
# -------------------------

errors = []

for i, row in enumerate(rows):

    if predictions[i] != labels[i]:

        errors.append({
            "text": row["text"],
            "label": int(labels[i]),
            "pred": int(predictions[i]),
            "prob": float(
                probabilities[i]
            ),
            "lang": row["lang"],
        })


print(
    f"\n=== ERRORS ({len(errors)}) ==="
)

for error in sorted(
    errors,
    key=lambda x: abs(
        x["prob"] - 0.5
    ),
):

    print(
        f'\nP={error["prob"]:.4f} '
        f'true={error["label"]} '
        f'pred={error["pred"]} '
        f'lang={error["lang"]}'
    )

    print(
        error["text"]
    )


# -------------------------
# Borderline examples
# -------------------------

borderline = sorted(
    zip(
        rows,
        probabilities,
        predictions,
    ),
    key=lambda item: abs(
        item[1] - 0.5
    ),
)


print(
    "\n=== 20 MOST BORDERLINE ==="
)

for row, probability, prediction in borderline[:20]:

    print(
        f'\nP={probability:.4f} '
        f'true={row["label"]} '
        f'pred={prediction}'
    )

    print(
        row["text"]
    )


# -------------------------
# Three-state product result
# -------------------------

text_only = 0
uncertain = 0
vision_now = 0

for probability in probabilities:

    if probability >= capture_threshold:
        vision_now += 1

    elif probability >= ask_threshold:
        uncertain += 1

    else:
        text_only += 1


print(
    "\n=== PRODUCT ROUTING ==="
)

print(
    "TEXT_ONLY:",
    text_only,
)

print(
    "UNCERTAIN:",
    uncertain,
)

print(
    "VISION_NOW:",
    vision_now,
)