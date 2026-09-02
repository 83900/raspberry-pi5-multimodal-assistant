import json
import random
from pathlib import Path
from collections import defaultdict


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

INPUT_FILE = DATA_DIR / "all.jsonl"

TRAIN_FILE = DATA_DIR / "train.jsonl"
VALIDATION_FILE = DATA_DIR / "validation.jsonl"
TEST_FILE = DATA_DIR / "test.jsonl"

RANDOM_SEED = 42


def load_jsonl(path):
    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                rows.append(json.loads(line))

    return rows


def save_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


rows = load_jsonl(INPUT_FILE)

groups = defaultdict(list)

for row in rows:
    groups[row["group"]].append(row)

group_names = list(groups.keys())

random.Random(RANDOM_SEED).shuffle(group_names)

n_groups = len(group_names)

n_train = max(1, round(n_groups * 0.70))
n_validation = max(1, round(n_groups * 0.15))

# 保证 test 至少还有一个 group
if n_train + n_validation >= n_groups:
    n_train = max(1, n_groups - 2)
    n_validation = 1

train_groups = set(
    group_names[:n_train]
)

validation_groups = set(
    group_names[
        n_train:n_train + n_validation
    ]
)

test_groups = set(
    group_names[
        n_train + n_validation:
    ]
)


train = []
validation = []
test = []

for group_name, group_rows in groups.items():

    if group_name in train_groups:
        train.extend(group_rows)

    elif group_name in validation_groups:
        validation.extend(group_rows)

    else:
        test.extend(group_rows)


save_jsonl(TRAIN_FILE, train)
save_jsonl(VALIDATION_FILE, validation)
save_jsonl(TEST_FILE, test)


print(
    f"groups={n_groups}, "
    f"train={len(train)}, "
    f"validation={len(validation)}, "
    f"test={len(test)}"
)

print(
    "train groups:",
    sorted(train_groups),
)

print(
    "validation groups:",
    sorted(validation_groups),
)

print(
    "test groups:",
    sorted(test_groups),
)