"""Tests for the scoring functions, using tiny hand-made inputs (no Gemini)."""

import pytest

from metrics import (
    average,
    breakdown,
    facts_present,
    first_hit_rank,
    hit_at_k,
    missing_facts,
    normalize,
    pages_found,
    reciprocal_rank,
    unique_pages,
)

A1, A2, A3, B1, B2 = ("a.pdf", 1), ("a.pdf", 2), ("a.pdf", 3), ("b.pdf", 1), ("b.pdf", 2)


# ---------- Retrieval ----------


def test_unique_pages_keeps_first_occurrence_in_order():
    assert unique_pages([A1, A2, A1, B1, A2]) == [A1, A2, B1]


def test_repeated_chunks_of_one_page_do_not_push_the_correct_page_down():
    # Three chunks from page A1, then the correct page: it is the 2nd PAGE, not the 4th chunk.
    assert first_hit_rank([A1, A1, A1, B1], [B1]) == 2


def test_hit_at_k():
    ranked = [A1, A2, B1, B2]
    assert hit_at_k(ranked, [A1], k=1)
    assert not hit_at_k(ranked, [B1], k=1)
    assert hit_at_k(ranked, [B1], k=3)
    assert not hit_at_k(ranked, [A3], k=5)  # never retrieved


def test_any_expected_page_counts_as_a_hit():
    # The fact is on two pages; finding either one is enough.
    assert first_hit_rank([B2, A2, A1], [A1, A2]) == 2


def test_same_page_number_in_another_file_is_not_a_hit():
    assert first_hit_rank([B1], [A1]) is None


@pytest.mark.parametrize(
    ("ranked", "expected_rr"),
    [([A1, A2, A3], 1.0), ([A2, A1, A3], 0.5), ([A2, A3, A1], 1 / 3), ([A2, A3], 0.0), ([], 0.0)],
)
def test_reciprocal_rank(ranked, expected_rr):
    assert reciprocal_rank(ranked, [A1]) == pytest.approx(expected_rr)


def test_mrr_is_the_average_of_reciprocal_ranks():
    # 1st, 2nd and missing -> (1 + 0.5 + 0) / 3 = 0.5
    ranks = [reciprocal_rank([A1, A2], [A1]), reciprocal_rank([A2, A1], [A1]), reciprocal_rank([A2], [A1])]
    assert average(ranks) == pytest.approx(0.5)


def test_pages_found_counts_each_expected_page_once():
    assert pages_found([A1, A1, B2], [A1, B1]) == 1
    assert pages_found([A1, B1], [A1, B1]) == 2


# ---------- Answers ----------


def test_normalize_lowercases_and_drops_thousands_separators():
    assert normalize("  The IX-1500 makes 1,500  Liters ") == "the ix-1500 makes 1500 liters"
    assert normalize("38,500 and 1,234,567") == "38500 and 1234567"


def test_normalize_keeps_commas_that_are_not_thousands_separators():
    assert normalize("1,2,3") == "1,2,3"
    assert normalize("Hello, world") == "hello, world"


def test_any_spelling_of_a_fact_is_accepted():
    facts = [["1,500", "1500"], ["hour"]]
    assert facts_present("It purifies 1500 liters per hour.", facts)
    assert facts_present("It purifies 1,500 liters per HOUR.", facts)


def test_every_fact_group_must_be_present():
    facts = [["38,500", "38500"], ["41,000", "41000"]]
    answer = "The handbook says it costs $38,500."
    assert not facts_present(answer, facts)
    assert missing_facts(answer, facts) == [["41,000", "41000"]]


def test_a_number_inside_a_longer_number_does_not_match():
    assert not facts_present("The company has 2400 employees.", [["240"]])
    assert not facts_present("Replace it every 13 months.", [["3 months"]])
    assert facts_present("Replace it every 3 months.", [["3 months"]])


def test_hebrew_facts():
    assert facts_present("עובד עם 8 שנות ותק מקבל 24 ימי חופשה.", [["24"]])
    assert facts_present("המנכ\"לית היא מרים אדלר.", [["מרים אדלר"]])
    assert not facts_present("עובד מקבל 20 ימי חופשה.", [["24"]])


# ---------- Summaries ----------


def test_average_skips_not_applicable_values():
    assert average([True, False, None, True]) == pytest.approx(2 / 3)
    assert average([None, None]) is None


def test_breakdown_by_language_and_type():
    records = [
        {"language": "en", "type": "factual", "hit": True},
        {"language": "en", "type": "factual", "hit": False},
        {"language": "he", "type": "factual", "hit": True},
        {"language": "he", "type": "not_found", "hit": None},  # metric does not apply
    ]
    result = breakdown(records, "hit")
    assert result["overall"] == {"value": pytest.approx(2 / 3), "count": 3}
    assert result["by_language"]["en"] == {"value": 0.5, "count": 2}
    assert result["by_language"]["he"] == {"value": 1.0, "count": 1}
    assert result["by_type"]["not_found"] == {"value": None, "count": 0}
