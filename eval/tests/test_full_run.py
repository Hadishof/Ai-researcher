"""Tests for answer scoring and the cached Gemini client (Gemini replaced by a fake)."""

from types import SimpleNamespace

import pytest
from google.genai import types
from google.genai.errors import ClientError

import cached_client
from app.schemas.chat import ChatResponse, Source
from app.services.generation import GeminiAnswer
from cache import GenerationCache
from cached_client import CachedGeminiClient, DailyLimitReached, is_daily_limit
from dataset import Question
from full_run import Outcome, failure, score
from run_eval import daily_limit_message


def make_question(qid="q", qtype="factual", pages=(("a.pdf", 1),), facts=(("1500", "1,500"),)) -> Question:
    expect_found = qtype != "not_found"
    return Question(
        id=qid,
        question="?",
        language="en",
        type=qtype,
        documents=["a.pdf", "b.pdf"],
        expect_found=expect_found,
        expected_pages=[{"file": f, "page": p} for f, p in pages] if expect_found else [],
        require_all_pages=qtype == "conflict",
        expected_facts=[list(group) for group in facts] if expect_found else [],
        history=[{"role": "user", "content": "earlier"}] if qtype == "follow_up" else [],
    )


def outcome(question: Question, answer: str, found: bool, cited=()) -> Outcome:
    sources = [Source(document_id="d", filename=f, page=p, score=0.8) for f, p in cited]
    return Outcome(question, question.question, [], [], ChatResponse(answer=answer, found=found, sources=sources))


def test_correct_answer_with_the_right_page():
    o = outcome(make_question(), "It makes 1,500 liters.", True, [("a.pdf", 1)])
    record = score(o)
    assert record["correct"] and record["facts_correct"] and record["cited_correct_page"]
    assert record["found_ok"]
    assert failure(o, record) is None


def test_missing_fact_is_a_failure_that_names_the_fact():
    o = outcome(make_question(), "It makes 1,200 liters.", True, [("a.pdf", 1)])
    record = score(o)
    assert record["correct"] is False
    assert failure(o, record)["problems"] == ["missing: 1500 / 1,500"]


def test_saying_not_found_for_an_answerable_question():
    o = outcome(make_question(), "I couldn't find this in the documents.", False)
    record = score(o)
    assert record["correct"] is False and record["found_ok"] is False
    assert failure(o, record)["problems"] == ["said not found (nothing passed the filters)"]


def test_not_found_question():
    right = outcome(make_question(qtype="not_found"), "I couldn't find this in the documents.", False)
    wrong = outcome(make_question(qtype="not_found"), "Yes, it has a pool.", True, [("a.pdf", 2)])
    assert score(right)["correct"] is True and score(right)["facts_correct"] is None
    assert score(wrong)["correct"] is False
    assert failure(wrong, score(wrong))["problems"] == ["answered, but the documents do not contain the answer"]


def test_conflict_needs_both_facts_and_both_pages():
    q = make_question(qtype="conflict", pages=(("a.pdf", 2), ("b.pdf", 2)), facts=(("38,500",), ("41,000",)))
    both = outcome(q, "One says 38,500, the other 41,000.", True, [("a.pdf", 2), ("b.pdf", 2)])
    one_page = outcome(q, "One says 38,500, the other 41,000.", True, [("a.pdf", 2)])
    assert score(both)["conflict_ok"] is True
    assert score(one_page)["conflict_ok"] is False
    assert failure(one_page, score(one_page))["problems"] == ["not every conflicting page cited"]


def test_follow_up_is_scored_on_its_facts():
    record = score(outcome(make_question(qtype="follow_up"), "Every 1500 hours.", True, [("a.pdf", 1)]))
    assert record["follow_up_ok"] is True
    assert record["conflict_ok"] is None


# ---------- Cached client ----------


class FakeModels:
    def __init__(self, replies):
        self.replies = list(replies)  # a string to return, or an exception to raise
        self.calls = 0

    def generate_content(self, model, contents, config):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


@pytest.fixture
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(cached_client.time, "sleep", waits.append)
    return waits


STRUCTURED = types.GenerateContentConfig(response_mime_type="application/json", response_schema=GeminiAnswer)
REPLY = '{"answer": "It makes 1500 liters.", "used_excerpts": [1]}'


def test_second_identical_request_is_served_from_the_cache(tmp_path, no_sleep):
    fake = SimpleNamespace(models=FakeModels([REPLY]))
    client = CachedGeminiClient(fake, GenerationCache(tmp_path), pace_seconds=0)

    first = client.models.generate_content(model="m", contents="prompt", config=STRUCTURED)
    second = client.models.generate_content(model="m", contents="prompt", config=STRUCTURED)

    assert fake.models.calls == 1  # the second answer came from disk
    assert first.parsed == second.parsed == GeminiAnswer(answer="It makes 1500 liters.", used_excerpts=[1])
    # A new client (a new run) still finds it: the cache is on disk.
    again = CachedGeminiClient(SimpleNamespace(models=FakeModels([])), GenerationCache(tmp_path), 0)
    assert again.models.generate_content(model="m", contents="prompt", config=STRUCTURED).text == REPLY


def test_a_different_prompt_is_not_served_from_the_cache(tmp_path, no_sleep):
    fake = SimpleNamespace(models=FakeModels([REPLY, REPLY]))
    client = CachedGeminiClient(fake, GenerationCache(tmp_path), pace_seconds=0)
    client.models.generate_content(model="m", contents="prompt A", config=STRUCTURED)
    client.models.generate_content(model="m", contents="prompt B", config=STRUCTURED)
    assert fake.models.calls == 2


def test_rate_limit_is_retried_after_waiting(tmp_path, no_sleep):
    rate_limited = ClientError(429, {"error": {"message": "Please retry in 7s."}})
    fake = SimpleNamespace(models=FakeModels([rate_limited, REPLY]))
    client = CachedGeminiClient(fake, GenerationCache(tmp_path), pace_seconds=0)

    response = client.models.generate_content(model="m", contents="prompt", config=STRUCTURED)

    assert response.parsed.answer == "It makes 1500 liters."
    assert 8 in no_sleep  # waited the 7 seconds Gemini asked for, plus 1


def daily_limit_error() -> ClientError:
    """Shaped like Gemini's real reply when the free tier's daily limit is used up."""
    return ClientError(429, {"error": {
        "code": 429,
        "message": "Quota exceeded ... Please retry in 10h46m5.05s.",
        "status": "RESOURCE_EXHAUSTED",
        "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}],
    }})


def test_daily_limit_stops_at_once_without_retrying(tmp_path, no_sleep):
    fake = SimpleNamespace(models=FakeModels([daily_limit_error(), REPLY]))
    client = CachedGeminiClient(fake, GenerationCache(tmp_path), pace_seconds=0)

    with pytest.raises(DailyLimitReached):
        client.models.generate_content(model="m", contents="prompt", config=STRUCTURED)

    assert fake.models.calls == 1  # no retry
    assert no_sleep == []  # and no waiting
    assert not list(tmp_path.iterdir())  # nothing cached


def test_per_minute_limit_is_not_mistaken_for_the_daily_one():
    per_minute = ClientError(429, {"error": {"message": "Please retry in 7s.", "details": [
        {"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}})
    assert not is_daily_limit(per_minute)
    assert is_daily_limit(daily_limit_error())


def test_daily_limit_message_says_how_far_the_run_got():
    message = daily_limit_message(11, 19)
    assert "11 of 19 questions are done" in message
    assert "same command tomorrow" in message


def test_other_client_errors_are_not_retried(tmp_path, no_sleep):
    fake = SimpleNamespace(models=FakeModels([ClientError(400, {"error": {"message": "bad request"}})]))
    client = CachedGeminiClient(fake, GenerationCache(tmp_path), pace_seconds=0)
    with pytest.raises(ClientError):
        client.models.generate_content(model="m", contents="prompt", config=STRUCTURED)
