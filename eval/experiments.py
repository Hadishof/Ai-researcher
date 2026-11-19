"""
The retrieval experiments: search every question in a temporary index, then score.

No Gemini calls happen here: every embedding comes from the cache (embedder.py
fills it first). The search and the relevance filters are the app's own code
(VectorStore.search and filter_results), so the numbers describe the real app.
"""

from dataclasses import dataclass
from pathlib import Path

from app.db.vector_store import SearchResult, StoredChunk, VectorStore
from app.services.retrieval import filter_results
from cache import EmbeddingCache
from chunkers import Chunk, PdfFile, Setup
from dataset import Question
from embedder import DOCUMENT, QUERY
from metrics import breakdown, hit_at_k, pages_found, reciprocal_rank

# How many chunks to fetch per question for the ranking metrics. Deeper than the
# app's top_k, so MRR can still see a correct page ranked 6th or 10th.
RANK_DEPTH = 20

# Values tried in the sweeps. With 40 dev questions, a finer grid would only fit noise.
THRESHOLDS = [round(0.26 + 0.02 * step, 2) for step in range(13)]  # 0.26 ... 0.50
MARGINS = [0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, None]  # None = relative filter off
MARGIN_OFF = 2.0  # cosine distance is at most 2, so this margin never drops anything

RANKING_METRICS = ["hit@1", "hit@3", "hit@5", "mrr"]


@dataclass
class QuestionSearch:
    """One question and the chunks the search returned for it, closest first."""

    question: Question
    results: list[SearchResult]


def build_index(folder: Path, setup: Setup, chunks: list[Chunk], cache: EmbeddingCache) -> VectorStore:
    """A fresh ChromaDB collection for one setup, in a temporary folder (never the app's data)."""
    store = VectorStore(path=str(folder), collection_name=setup.name)
    store.add_chunks(
        [
            StoredChunk(
                id=f"{chunk.document_id}-{index}",
                text=chunk.text,
                embedding=cache.get(chunk.text, DOCUMENT),
                document_id=chunk.document_id,
                filename=chunk.filename,
                page=chunk.page,
                page_count=chunk.page_count,
            )
            for index, chunk in enumerate(chunks)
        ]
    )
    return store


def search_all(
    store: VectorStore, questions: list[Question], pdfs: list[PdfFile], cache: EmbeddingCache
) -> list[QuestionSearch]:
    """Search each question only in its own documents, like a chat that selected them."""
    ids_by_filename = {pdf.filename: pdf.document_id for pdf in pdfs}
    searches = []
    for question in questions:
        document_ids = [ids_by_filename[name] for name in question.documents]
        embedding = cache.get(question.question, QUERY)
        results = store.search(embedding, top_k=RANK_DEPTH, document_ids=document_ids)
        searches.append(QuestionSearch(question, results))
    return searches


def pages_of(results: list[SearchResult]) -> list[tuple[str, int]]:
    return [(result.filename, result.page) for result in results]


def expected_pages_of(question: Question) -> list[tuple[str, int]]:
    return [(page.file, page.page) for page in question.expected_pages]


# ---------- Ranking (before the relevance filters) ----------


def ranking_record(search: QuestionSearch) -> dict:
    """Hit@k and reciprocal rank for one question. Not applicable (None) to not_found questions."""
    question = search.question
    record = {"id": question.id, "language": question.language, "type": question.type}
    if not question.expect_found:
        return record | {name: None for name in RANKING_METRICS}
    ranked, expected = pages_of(search.results), expected_pages_of(question)
    return record | {
        "hit@1": hit_at_k(ranked, expected, 1),
        "hit@3": hit_at_k(ranked, expected, 3),
        "hit@5": hit_at_k(ranked, expected, 5),
        "mrr": reciprocal_rank(ranked, expected),
    }


def ranking_summary(searches: list[QuestionSearch]) -> dict:
    records = [ranking_record(search) for search in searches]
    return {
        "metrics": {name: breakdown(records, name) for name in RANKING_METRICS},
        "records": records,
    }


# ---------- Relevance filters (what actually reaches the LLM) ----------


def filter_scores(
    searches: list[QuestionSearch], top_k: int, max_distance: float, margin: float
) -> dict:
    """
    Apply the app's filters to the app's top_k results, and count what survives.

    - answerable questions: is the correct page still there? (for a conflict,
      ALL its pages must still be there, otherwise the LLM can't report both sides)
    - not_found questions: was everything dropped, so the app says "not found"
      without calling the LLM?
    """
    page_kept = blocked = conflicts_ok = chunks_sent = 0
    answerable = not_found = conflicts = 0
    for search in searches:
        kept = filter_results(search.results[:top_k], max_distance, margin)
        chunks_sent += len(kept)
        question = search.question
        if not question.expect_found:
            not_found += 1
            blocked += not kept
            continue
        answerable += 1
        expected = expected_pages_of(question)
        found = pages_found(pages_of(kept), expected)
        if question.require_all_pages:
            conflicts += 1
            conflicts_ok += found == len(expected)
            page_kept += found == len(expected)
        else:
            page_kept += found > 0
    return {
        "page_kept": page_kept,
        "answerable": answerable,
        "blocked": blocked,
        "not_found": not_found,
        "conflicts_all_pages": conflicts_ok,
        "conflicts": conflicts,
        "avg_chunks_sent": chunks_sent / len(searches) if searches else 0.0,
    }


def threshold_sweep(searches: list[QuestionSearch], top_k: int, margin: float) -> list[dict]:
    return [
        {"max_distance": value} | filter_scores(searches, top_k, value, margin)
        for value in THRESHOLDS
    ]


def margin_sweep(searches: list[QuestionSearch], top_k: int, max_distance: float) -> list[dict]:
    return [
        {"margin": value} | filter_scores(searches, top_k, max_distance, value if value is not None else MARGIN_OFF)
        for value in MARGINS
    ]


def find_misses(
    searches: list[QuestionSearch], top_k: int, max_distance: float, margin: float
) -> list[dict]:
    """Every question that goes wrong at the given settings, with what came back instead."""
    misses = []
    for search in searches:
        question = search.question
        kept = filter_results(search.results[:top_k], max_distance, margin)
        expected = expected_pages_of(question)
        found_in_top_k = pages_found(pages_of(search.results[:top_k]), expected)
        found_after_filter = pages_found(pages_of(kept), expected)
        needed = len(expected) if question.require_all_pages else 1

        if not question.expect_found:
            problem = "not blocked" if kept else None
        elif found_in_top_k < needed:
            problem = f"page not in top {top_k}"
        elif found_after_filter < needed:
            problem = "page dropped by filters"
        else:
            problem = None

        if problem:
            misses.append({
                "id": question.id,
                "language": question.language,
                "type": question.type,
                "problem": problem,
                "question": question.question,
                "expected": [f"{file} p.{page}" for file, page in expected],
                "got": [f"{r.filename} p.{r.page} ({r.distance:.3f})" for r in search.results[:3]],
            })
    return misses


# ---------- The "best settings" rules (fixed before looking at any result) ----------


def pick_best_setup(overall: dict[str, dict[str, float]], default: str) -> str:
    """
    Highest MRR; ties broken by Hit@1. If still tied, keep the app's current
    setting (`default`): no change without evidence.
    `overall` maps setup name -> {"mrr": ..., "hit@1": ...}.
    """
    def score(name: str) -> tuple:
        return (overall[name]["mrr"], overall[name]["hit@1"], name == default)

    return max(overall, key=score)


def pick_threshold(rows: list[dict]) -> float:
    """
    The MAX_DISTANCE that gets the most questions right: correct pages kept
    plus not_found questions blocked. When several values tie, take the middle
    one (the lower of the two middles for an even count), so the limit sits as
    far as possible from both kinds of mistakes.
    """
    best = max(row["page_kept"] + row["blocked"] for row in rows)
    tied = [row["max_distance"] for row in rows if row["page_kept"] + row["blocked"] == best]
    return tied[(len(tied) - 1) // 2]


def pick_margin(rows: list[dict]) -> float | None:
    """
    The smallest margin that loses nothing: it keeps as many correct pages and
    complete conflicts as the best row. A smaller margin sends fewer, more
    relevant chunks to the LLM. None means the relative filter is not needed.
    """
    def kept(row: dict) -> tuple:
        return (row["page_kept"], row["conflicts_all_pages"])

    best = max(kept(row) for row in rows)
    for row in rows:  # rows go from the smallest margin to "off"
        if kept(row) == best:
            return row["margin"]
    return None
