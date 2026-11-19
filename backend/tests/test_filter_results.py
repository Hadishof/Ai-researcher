"""Tests for the two relevance filters on their own (no search, no Gemini)."""

from app.db.vector_store import SearchResult
from app.services.retrieval import filter_results


def result(distance: float) -> SearchResult:
    return SearchResult(text="", document_id="doc", filename="a.pdf", page=1, distance=distance)


def distances(results: list[SearchResult]) -> list[float]:
    return [r.distance for r in results]


def test_absolute_limit_drops_chunks_that_are_too_far():
    kept = filter_results([result(0.20), result(0.30), result(0.40)], max_distance=0.35, relative_margin=1)
    assert distances(kept) == [0.20, 0.30]


def test_relative_margin_drops_chunks_much_worse_than_the_best():
    kept = filter_results([result(0.20), result(0.24), result(0.30)], max_distance=1, relative_margin=0.05)
    assert distances(kept) == [0.20, 0.24]


def test_nothing_kept_when_even_the_best_chunk_is_too_far():
    assert filter_results([result(0.50)], max_distance=0.38, relative_margin=0.05) == []
    assert filter_results([], max_distance=0.38, relative_margin=0.05) == []
