import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, precision_score, recall_score


MODEL_NAME = "intfloat/multilingual-e5-small"

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ARTIFACT_DIR = ROOT.parent.parent / "artifacts" / "vision_intent"

ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def load_jsonl(path: Path):
    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                rows.append(json.loads(line))

    return rows


def encode(model, rows):
    texts = [
        "query: " + row["text"].strip()
        for row in rows
    ]

    return model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    )


train = load_jsonl(DATA_DIR / "train.jsonl")
validation = load_jsonl(DATA_DIR / "validation.jsonl")
test = load_jsonl(DATA_DIR / "test.jsonl")

print(
    f"train={len(train)}, "
    f"validation={len(validation)}, "
    f"test={len(test)}"
)


encoder = SentenceTransformer(MODEL_NAME)

print("Encoding training data...")
x_train = encode(encoder, train)

print("Encoding validation data...")
x_validation = encode(encoder, validation)

print("Encoding test data...")
x_test = encode(encoder, test)


y_train = np.array([
    row["label"]
    for row in train
])

y_validation = np.array([
    row["label"]
    for row in validation
])

y_test = np.array([
    row["label"]
    for row in test
])


head = LogisticRegression(
    C=1.0,
    max_iter=2000,
    random_state=42,
)

print("Training logistic regression head...")

head.fit(
    x_train,
    y_train,
)


validation_probability = (
    head.predict_proba(x_validation)[:, 1]
)

best_threshold = None
best_recall = -1.0

for threshold in np.arange(
    0.50,
    0.991,
    0.005,
):
    prediction = (
        validation_probability >= threshold
    ).astype(int)

    precision = precision_score(
        y_validation,
        prediction,
        zero_division=0,
    )

    recall = recall_score(
        y_validation,
        prediction,
        zero_division=0,
    )

    if (
        precision >= 0.98
        and recall > best_recall
    ):
        best_threshold = float(threshold)
        best_recall = float(recall)


if best_threshold is None:
    print(
        "WARNING: validation set did not "
        "reach 98% precision."
    )

    best_threshold = 0.85


print(
    "capture threshold:",
    best_threshold,
)


test_probability = (
    head.predict_proba(x_test)[:, 1]
)

test_prediction = (
    test_probability >= best_threshold
).astype(int)


print(
    classification_report(
        y_test,
        test_prediction,
        digits=4,
    )
)


np.savez(
    ARTIFACT_DIR / "vision_intent_head.npz",

    weight=head.coef_[0].astype(
        np.float32
    ),

    bias=np.float32(
        head.intercept_[0]
    ),

    capture_threshold=np.float32(
        best_threshold
    ),

    ask_threshold=np.float32(
        0.40
    ),
)


print(
    "saved:",
    ARTIFACT_DIR
    / "vision_intent_head.npz"
)