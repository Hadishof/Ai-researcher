"""
The full run: every question goes through the whole app pipeline, answer included.

For each question, exactly like POST /chat in a chat that selected its documents:
1. follow-up?  rewrite it into a standalone question (rewrite_question)
2. search its documents and apply the relevance filters (filter_results)
3. answer from the chunks that are left (answer_from_chunks, in app/services/answering.py)
Then the answer is checked against the expected facts and pages.
"""

from dataclasses import dataclass

from google.genai import types

from app.core.config import Settings
from app.db.conversation_store import Message
from app.db.vector_store import SearchResult
from app.schemas.chat import ChatResponse
from app.services.rewriting import REWRITE_INSTRUCTION, build_rewrite_prompt
from cache import GenerationCache
from cached_client import generation_key
from dataset import Question
from metrics import facts_present, hit_at_k, missing_facts, pages_found, reciprocal_rank

# Metrics reported for the full run, in this order. Each one is None for the
# questions it does not apply to (e.g. "facts_correct" for not_found questions).
ANSWER_METRICS = ["correct", "found_ok", "facts_correct", "cited_correct_page", "conflict_ok", "follow_up_ok"]
RETRIEVAL_METRICS = ["hit@1", "hit@5", "mrr"]


def history_messages(question: Question, limit: int) -> list[Message]:
    """The dataset's history as the app's Message objects (only role and content matter)."""
    recent = question.history[-limit:] if limit else []
    return [
        Message(id=index, conversation_id=0, role=m.role, content=m.content, found=None, sources=[], created_at="")
        for index, m in enumerate(recent)
    ]


def cached_rewrite(question: Question, settings: Settings, cache: GenerationCache) -> str | None:
    """
    For the dry run: this follow-up's rewritten question if it is already cached, else None.
    Uses the same request (and so the same cache key) as rewrite_question.
    """
    contents = build_rewrite_prompt(history_messages(question, settings.history_messages), question.question)
    config = types.GenerateContentConfig(system_instruction=REWRITE_INSTRUCTION, temperature=0)
    text = cache.get(generation_key(settings.generation_model, contents, config))
    if text is None:
        return None
    return text.strip() or question.question  # the same fallback as rewrite_question


@dataclass
class Outcome:
    """What the app produced for one question."""

    question: Question
    search_question: str  # the rewritten question for follow-ups, else the question
    ranked: list[SearchResult]  # the search results, closest first (deeper than top_k)
    kept: list[SearchResult]  # what passed the filters and was sent to Gemini
    response: ChatResponse


def pages(results) -> list[tuple[str, int]]:
    return [(r.filename, r.page) for r in results]


def score(outcome: Outcome) -> dict:
    """Check one answer. Every check is plain text/page matching: no LLM judge."""
    question, response = outcome.question, outcome.response
    expected = [(p.file, p.page) for p in question.expected_pages]
    cited = [(s.filename, s.page) for s in response.sources]
    answerable = question.expect_found

    facts_ok = (response.found and facts_present(response.answer, question.expected_facts)) if answerable else None
    all_pages_cited = pages_found(cited, expected) == len(expected)
    record = {
        "id": question.id,
        "language": question.language,
        "type": question.type,
        # Right outcome overall: the facts for an answerable question, "not found" otherwise.
        "correct": facts_ok if answerable else not response.found,
        "found_ok": response.found == question.expect_found,
        "facts_correct": facts_ok,
        "cited_correct_page": pages_found(cited, expected) > 0 if answerable else None,
        "conflict_ok": (facts_ok and all_pages_cited) if question.type == "conflict" else None,
        "follow_up_ok": facts_ok if question.type == "follow_up" else None,
    }
    ranked = pages(outcome.ranked)
    record |= {
        "hit@1": hit_at_k(ranked, expected, 1) if answerable else None,
        "hit@5": hit_at_k(ranked, expected, 5) if answerable else None,
        "mrr": reciprocal_rank(ranked, expected) if answerable else None,
    }
    return record


def failure(outcome: Outcome, record: dict) -> dict | None:
    """What went wrong for a question that is not fully correct, or None if it is fine."""
    question, response = outcome.question, outcome.response
    problems = []
    if question.expect_found and not response.found:
        problems.append("said not found" if outcome.kept else "said not found (nothing passed the filters)")
    elif not question.expect_found and response.found:
        problems.append("answered, but the documents do not contain the answer")
    elif question.expect_found:
        missing = missing_facts(response.answer, question.expected_facts)
        if missing:
            problems.append("missing: " + "; ".join(" / ".join(group) for group in missing))
        if record["cited_correct_page"] is False:
            problems.append("correct page not cited")
        if record["conflict_ok"] is False and not missing:
            problems.append("not every conflicting page cited")
    if not problems:
        return None
    return {
        "id": question.id,
        "language": question.language,
        "type": question.type,
        "problems": problems,
        "question": question.question,
        "search_question": outcome.search_question,
        "expected_facts": [" / ".join(group) for group in question.expected_facts] or ["(not found)"],
        "expected_pages": [f"{p.file} p.{p.page}" for p in question.expected_pages],
        "answer": response.answer,
        "sources": [f"{s.filename} p.{s.page}" for s in response.sources],
        "sent_to_gemini": [f"{r.filename} p.{r.page} ({r.distance:.3f})" for r in outcome.kept],
    }
