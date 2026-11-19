"""
Splits the questions into a dev set (for tuning) and a test set (for the final score).

Tuning settings on the same questions you report would overfit: the settings
would be chosen to fit those exact questions, and the score would look better
than it really is on new questions. So the experiments only see the dev set,
and the test set is used once, for the final numbers.

The split is stratified: each question type, and inside it each language, gets
about the same share of test questions as the whole dataset. A fixed random
seed makes the split identical every time. It is saved in eval/data/split.json.

Run from the eval/ folder:  python split.py
"""

import json
import math
import random
from collections import defaultdict
from pathlib import Path

from dataset import DATA_DIR, Question, load_dataset

SPLIT_PATH = DATA_DIR / "split.json"
SEED = 42
TEST_SIZE = 19


def allocate(group_sizes: dict[str, int], total: int, at_least_one: bool) -> dict[str, int]:
    """
    Share `total` test questions between groups in proportion to their size.

    Uses the "largest remainder" method: every group first gets the whole part of
    its fair share; the questions left over go to the groups with the largest
    fractions. With `at_least_one`, every group of 2 or more questions gets at least
    one test question, so no question type is missing from the test set.
    Ties are broken by group name, so the result never changes.
    """
    all_questions = sum(group_sizes.values())
    shares = {name: size * total / all_questions for name, size in group_sizes.items()}
    counts = {name: math.floor(share) for name, share in shares.items()}

    if at_least_one:
        for name, size in group_sizes.items():
            if size >= 2 and counts[name] == 0:
                counts[name] = 1

    remaining = total - sum(counts.values())
    by_fraction = sorted(group_sizes, key=lambda name: (-(shares[name] % 1), name))
    for name in by_fraction:
        if remaining <= 0:
            break
        # Skip groups already raised to their minimum (they got their extra question)
        # and groups that have no questions left to give.
        if counts[name] == math.floor(shares[name]) and counts[name] < group_sizes[name]:
            counts[name] += 1
            remaining -= 1
    return counts


def make_split(questions: list[Question], test_size: int = TEST_SIZE, seed: int = SEED) -> dict:
    """Return {"seed", "dev": [ids], "test": [ids]}. Same input -> same split."""
    rng = random.Random(seed)  # own random generator: not affected by other code

    by_type: dict[str, list[Question]] = defaultdict(list)
    for question in questions:
        by_type[question.type].append(question)

    # 1. How many test questions each type gets (at least one per type).
    type_counts = allocate(
        {name: len(group) for name, group in by_type.items()}, test_size, at_least_one=True
    )

    test_ids: list[str] = []
    for type_name in sorted(by_type):
        # 2. Inside the type, share its test questions between the languages.
        by_language: dict[str, list[Question]] = defaultdict(list)
        for question in by_type[type_name]:
            by_language[question.language].append(question)
        language_counts = allocate(
            {name: len(group) for name, group in by_language.items()},
            type_counts[type_name],
            at_least_one=False,
        )
        # 3. Pick the test questions at random (seeded) inside each (type, language) group.
        for language in sorted(by_language):
            ids = sorted(question.id for question in by_language[language])
            rng.shuffle(ids)
            test_ids.extend(ids[: language_counts[language]])

    test = set(test_ids)
    if len(test) != test_size:
        raise ValueError(f"Expected {test_size} test questions, got {len(test)}.")
    return {
        "seed": seed,
        "dev": sorted(question.id for question in questions if question.id not in test),
        "test": sorted(test),
    }


def load_split(path: Path = SPLIT_PATH) -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def main() -> None:
    questions = load_dataset()
    split = make_split(questions)
    if SPLIT_PATH.exists() and load_split() != split:
        raise SystemExit(
            f"{SPLIT_PATH.name} already exists and differs from a fresh split. "
            "The split must never change once tuning has started; delete the file "
            "only if you really mean to create a new split."
        )
    with open(SPLIT_PATH, "w", encoding="utf-8") as file:
        json.dump(split, file, indent=2)
        file.write("\n")
    print(f"Saved {SPLIT_PATH.name}: {len(split['dev'])} dev, {len(split['test'])} test")


if __name__ == "__main__":
    main()
