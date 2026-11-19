"""Tests for the dataset loader and the dev/test split (no Gemini)."""

import json
from collections import Counter

import pytest

from dataset import load_dataset
from split import TEST_SIZE, allocate, load_split, make_split


@pytest.fixture(scope="module")
def questions():
    return load_dataset()


# ---------- Dataset ----------


def test_real_dataset_loads(questions):
    assert len(questions) == 59
    assert len({question.id for question in questions}) == 59


def _write_row(tmp_path, **changes):
    """A valid one-row dataset (with a fake PDF next to it), with some fields changed."""
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-")
    row = {
        "id": "x-01",
        "question": "Who is the CEO?",
        "language": "en",
        "type": "factual",
        "documents": ["doc.pdf"],
        "expect_found": True,
        "expected_pages": [{"file": "doc.pdf", "page": 1}],
        "require_all_pages": False,
        "expected_facts": [["Miriam Adler"]],
        "history": [],
    }
    row.update(changes)
    path = tmp_path / "dataset.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def test_valid_row_loads(tmp_path):
    assert load_dataset(_write_row(tmp_path))[0].id == "x-01"


@pytest.mark.parametrize(
    "changes",
    [
        {"language": "fr"},  # unknown language
        {"expected_fact": [["x"]]},  # misspelled field name
        {"expected_pages": [{"file": "other.pdf", "page": 1}]},  # page from an unselected file
        {"type": "not_found"},  # not_found but expect_found is true
        {"type": "follow_up"},  # follow-up without history
        {"type": "conflict"},  # conflict without require_all_pages
        {"documents": ["missing.pdf"], "expected_pages": [{"file": "missing.pdf", "page": 1}]},
    ],
)
def test_invalid_rows_are_rejected_with_the_line_number(tmp_path, changes):
    with pytest.raises(ValueError, match="line 1"):
        load_dataset(_write_row(tmp_path, **changes))


# ---------- Split ----------


def test_split_is_deterministic(questions):
    assert make_split(questions) == make_split(questions)


def test_split_has_no_overlap_and_covers_every_question(questions):
    split = make_split(questions)
    dev, test = set(split["dev"]), set(split["test"])
    assert not dev & test
    assert dev | test == {question.id for question in questions}
    assert len(test) == TEST_SIZE
    assert len(dev) == len(questions) - TEST_SIZE


def test_saved_split_matches_a_fresh_split(questions):
    """split.json must never drift: if the dataset or the code changes the split, this fails."""
    assert load_split() == make_split(questions)


def test_every_question_type_is_in_both_sets(questions):
    split = make_split(questions)
    test_ids = set(split["test"])
    test_types = Counter(q.type for q in questions if q.id in test_ids)
    dev_types = Counter(q.type for q in questions if q.id not in test_ids)
    for question_type in {q.type for q in questions}:
        assert test_types[question_type] >= 1
        assert dev_types[question_type] >= 1


def test_allocate_is_proportional_and_gives_small_groups_one():
    counts = allocate({"big": 30, "medium": 7, "small": 2}, total=13, at_least_one=True)
    assert sum(counts.values()) == 13
    assert counts["small"] == 1
    assert counts["big"] > counts["medium"]
