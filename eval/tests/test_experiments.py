"""Tests for the experiment scoring, the "best settings" rules and the cache (no Gemini)."""

from app.db.vector_store import SearchResult
from cache import EmbeddingCache
from dataset import Question
from experiments import (
    QuestionSearch,
    filter_scores,
    find_misses,
    pick_best_setup,
    pick_margin,
    pick_threshold,
)


def make_question(qid: str, expect_found: bool = True, pages=((1,),), conflict: bool = False) -> Question:
    return Question(
        id=qid,
        question="?",
        language="en",
        type="conflict" if conflict else ("factual" if expect_found else "not_found"),
        documents=["a.pdf"],
        expect_found=expect_found,
        expected_pages=[{"file": "a.pdf", "page": p[0]} for p in pages] if expect_found else [],
        require_all_pages=conflict,
        expected_facts=[["x"]] if expect_found else [],
        history=[],
    )


def results(*page_distance: tuple[int, float]) -> list[SearchResult]:
    return [SearchResult("", "doc", "a.pdf", page, distance) for page, distance in page_distance]


# ---------- Filter scores ----------


def test_filter_scores_counts_kept_pages_and_blocked_questions():
    searches = [
        QuestionSearch(make_question("ok"), results((1, 0.20), (2, 0.30))),  # page 1 kept
        QuestionSearch(make_question("far"), results((1, 0.45))),  # page 1 too far: dropped
        QuestionSearch(make_question("nf", expect_found=False), results((3, 0.50))),  # blocked
    ]
    scores = filter_scores(searches, top_k=5, max_distance=0.40, margin=0.05)
    assert (scores["page_kept"], scores["answerable"]) == (1, 2)
    assert (scores["blocked"], scores["not_found"]) == (1, 1)
    assert scores["avg_chunks_sent"] == 1 / 3  # only the 0.20 chunk survives


def test_conflict_needs_every_page_after_the_filters():
    conflict = make_question("cf", pages=((1,), (2,)), conflict=True)
    search = [QuestionSearch(conflict, results((1, 0.20), (2, 0.30)))]
    # A tight margin drops page 2 (0.30 > 0.20 + 0.05): the conflict is incomplete.
    assert filter_scores(search, 5, max_distance=0.40, margin=0.05)["conflicts_all_pages"] == 0
    assert filter_scores(search, 5, max_distance=0.40, margin=0.15)["conflicts_all_pages"] == 1


def test_only_the_top_k_results_count():
    search = [QuestionSearch(make_question("deep"), results((2, 0.20), (3, 0.21), (1, 0.22)))]
    assert filter_scores(search, top_k=2, max_distance=1, margin=1)["page_kept"] == 0
    assert filter_scores(search, top_k=3, max_distance=1, margin=1)["page_kept"] == 1


def test_find_misses_names_the_problem():
    searches = [
        QuestionSearch(make_question("good"), results((1, 0.20))),
        QuestionSearch(make_question("dropped"), results((1, 0.45))),
        QuestionSearch(make_question("nf", expect_found=False), results((3, 0.30))),
    ]
    misses = {m["id"]: m["problem"] for m in find_misses(searches, 5, 0.40, 0.05)}
    assert misses == {"dropped": "page dropped by filters", "nf": "not blocked"}


# ---------- Rules ----------


def test_best_setup_is_highest_mrr_then_hit1_then_current():
    assert pick_best_setup({"a": {"mrr": 0.8, "hit@1": 0.7}, "b": {"mrr": 0.9, "hit@1": 0.6}}, "a") == "b"
    assert pick_best_setup({"a": {"mrr": 0.9, "hit@1": 0.7}, "b": {"mrr": 0.9, "hit@1": 0.8}}, "a") == "b"
    assert pick_best_setup({"a": {"mrr": 0.9, "hit@1": 0.8}, "b": {"mrr": 0.9, "hit@1": 0.8}}, "a") == "a"


def row(max_distance: float, kept: int, blocked: int) -> dict:
    return {"max_distance": max_distance, "page_kept": kept, "blocked": blocked}


def test_threshold_picks_the_middle_of_the_best_values():
    rows = [row(0.30, 5, 4), row(0.32, 7, 4), row(0.34, 8, 3), row(0.36, 9, 2), row(0.38, 10, 0)]
    # 0.32, 0.34 and 0.36 all score 11: the middle one is chosen.
    assert pick_threshold(rows) == 0.34


def test_threshold_tie_with_even_count_takes_the_lower_middle():
    assert pick_threshold([row(0.30, 9, 2), row(0.32, 10, 1), row(0.34, 11, 0), row(0.36, 11, 0)]) == 0.32


def test_margin_is_the_smallest_that_loses_nothing():
    rows = [
        {"margin": 0.02, "page_kept": 8, "conflicts_all_pages": 0},
        {"margin": 0.05, "page_kept": 9, "conflicts_all_pages": 1},
        {"margin": 0.10, "page_kept": 9, "conflicts_all_pages": 2},
        {"margin": None, "page_kept": 9, "conflicts_all_pages": 2},
    ]
    assert pick_margin(rows) == 0.10


# ---------- Cache ----------


def test_cache_round_trip_and_separate_keys(tmp_path):
    cache = EmbeddingCache("model-a", folder=tmp_path)
    assert cache.get("hello", "RETRIEVAL_QUERY") is None
    cache.put("hello", "RETRIEVAL_QUERY", [0.1, 0.2])
    assert cache.get("hello", "RETRIEVAL_QUERY") == [0.1, 0.2]
    # Same text, but another task type or another model: a different entry.
    assert not cache.has("hello", "RETRIEVAL_DOCUMENT")
    assert not EmbeddingCache("model-b", folder=tmp_path).has("hello", "RETRIEVAL_QUERY")
