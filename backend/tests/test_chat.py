"""Tests for POST /chat: retrieval filters, sources, 'not found', and Gemini failures."""

import math

import pytest
from google.genai.errors import ClientError, ServerError

from app.services.generation import GeminiAnswer

HANDBOOK = [
    "Nimbus Robotics was founded by Dana Levi.",
    "Support responds to critical problems within 4 hours.",
    "העובדים מקבלים עשרים ימי חופשה בשנה",  # "Employees get twenty vacation days a year"
    "The maximum load of the robot arm is 50 kg.",
]


def at_distance(distance: float) -> list[float]:
    """A 2D vector whose cosine distance from [1, 0] is exactly `distance`."""
    similarity = 1 - distance
    return [similarity, math.sqrt(1 - similarity**2)]


def ask(client, question: str):
    return client.post("/chat", json={"question": question})


@pytest.fixture
def handbook_id(upload, make_pdf) -> str:
    """Upload the 4-page handbook and return its document id."""
    return upload(make_pdf(HANDBOOK), "handbook.pdf").json()["document_id"]


@pytest.fixture
def hr_pages(upload, make_pdf, fake_gemini) -> str:
    """
    Upload 4 pages whose distances from the question "salary" are known:

    page 1 salary   0.00  best match                      -> kept
    page 2 pension  0.03  within margin (0.05) of best    -> kept
    page 3 bonus    0.15  passes MAX_DISTANCE (0.38), but
                          too far from the best match     -> dropped by the RELATIVE filter
    page 4 parking  0.50  fails MAX_DISTANCE              -> dropped by the ABSOLUTE filter
    """
    fake_gemini.models.topics = {
        "salary": at_distance(0.0),
        "pension": at_distance(0.03),
        "bonus": at_distance(0.15),
        "parking": at_distance(0.50),
    }
    fake_gemini.models.other = [0.0, 1.0]
    pages = [
        "Salary is paid on the 10th of every month.",
        "The pension fund receives 6 percent of each paycheck.",
        "A yearly bonus depends on company results.",
        "Parking is free for all employees.",
    ]
    return upload(make_pdf(pages), "hr.pdf").json()["document_id"]


# --- Answers with sources ------------------------------------------------------


def test_answer_with_page_source(client, handbook_id, fake_gemini):
    fake_gemini.models.answer = GeminiAnswer(
        answer="Nimbus Robotics was founded by Dana Levi.", used_excerpts=[1]
    )

    response = ask(client, "Who founded Nimbus Robotics?")

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Nimbus Robotics was founded by Dana Levi.",
        "found": True,
        "sources": [
            {"document_id": handbook_id, "filename": "handbook.pdf", "page": 1, "score": 1.0}
        ],
    }
    # Gemini was called once, and only the relevant page was sent to it.
    [prompt] = fake_gemini.models.generate_calls
    assert "[Excerpt 1 | handbook.pdf, page 1]" in prompt
    assert "Support responds" not in prompt


def test_hebrew_question_answered_from_hebrew_page(client, handbook_id, fake_gemini):
    fake_gemini.models.answer = GeminiAnswer(
        answer="העובדים מקבלים עשרים ימי חופשה בשנה.", used_excerpts=[1]
    )

    response = ask(client, "כמה ימי חופשה בשנה מקבלים העובדים?")

    body = response.json()
    assert body["found"] is True
    assert body["answer"] == "העובדים מקבלים עשרים ימי חופשה בשנה."
    assert [source["page"] for source in body["sources"]] == [3]
    # The Hebrew text reached Gemini intact.
    assert "העובדים מקבלים עשרים ימי חופשה בשנה" in fake_gemini.models.generate_calls[0]


# --- "Not found" ---------------------------------------------------------------


def test_not_found_when_nothing_passes_the_threshold(client, handbook_id, fake_gemini):
    response = ask(client, "What is the weather today?")  # unrelated to every page

    assert response.json() == {
        "answer": "I couldn't find this in the documents.",
        "found": False,
        "sources": [],
    }
    assert fake_gemini.models.generate_calls == []  # the LLM was NOT called


def test_not_found_answer_is_in_hebrew_for_a_hebrew_question(client, handbook_id, fake_gemini):
    response = ask(client, "מה מזג האוויר היום?")

    assert response.json()["answer"] == "לא מצאתי את זה במסמכים."
    assert response.json()["found"] is False
    assert fake_gemini.models.generate_calls == []


def test_not_found_when_no_documents_are_uploaded(client, fake_gemini):
    response = ask(client, "Who founded Nimbus Robotics?")

    assert response.json()["found"] is False
    assert fake_gemini.models.generate_calls == []


def test_not_found_when_the_llm_says_so(client, handbook_id, fake_gemini):
    # A chunk passed the filters, but the LLM decided it doesn't answer the question.
    fake_gemini.models.answer = GeminiAnswer(
        answer="I couldn't find this in the documents.", used_excerpts=[]
    )

    response = ask(client, "Who founded the robot arm company's competitor?")

    assert response.json()["found"] is False
    assert response.json()["sources"] == []
    assert len(fake_gemini.models.generate_calls) == 1


# --- Retrieval filters ---------------------------------------------------------


def test_relative_filter_removes_weak_chunks(client, hr_pages, fake_gemini):
    ask(client, "When is the salary paid?")

    [prompt] = fake_gemini.models.generate_calls
    assert "Salary is paid" in prompt  # 0.00: best match
    assert "pension fund" in prompt  # 0.03: close to the best
    assert "yearly bonus" not in prompt  # 0.15: removed by the relative filter
    assert "Parking" not in prompt  # 0.50: removed by MAX_DISTANCE


def test_weak_chunk_is_kept_when_the_margin_is_wide(client, hr_pages, fake_gemini, settings):
    # Control test: proves it was the relative filter (not MAX_DISTANCE) that removed "bonus".
    settings.relative_margin = 1.0

    ask(client, "When is the salary paid?")

    [prompt] = fake_gemini.models.generate_calls
    assert "yearly bonus" in prompt
    assert "Parking" not in prompt  # still removed by MAX_DISTANCE


# --- Sources = only the excerpts the LLM used ----------------------------------


def test_only_excerpts_the_llm_used_become_sources(client, hr_pages, fake_gemini):
    # Excerpt 1 = salary page, excerpt 2 = pension page. 99 doesn't exist and is ignored.
    fake_gemini.models.answer = GeminiAnswer(
        answer="The pension fund receives 6 percent of each paycheck.", used_excerpts=[2, 99]
    )

    response = ask(client, "When is the salary paid?")

    assert response.json()["sources"] == [
        {"document_id": hr_pages, "filename": "hr.pdf", "page": 2, "score": 0.97}
    ]


def test_answer_citing_no_valid_excerpt_is_not_found(client, hr_pages, fake_gemini):
    fake_gemini.models.answer = GeminiAnswer(answer="Some answer.", used_excerpts=[99])

    response = ask(client, "When is the salary paid?")

    assert response.json()["found"] is False


def test_one_source_per_page(client, upload, make_pdf, fake_gemini, settings):
    # A small chunk size splits this one page into two chunks, both about salary.
    settings.chunk_size = 60
    settings.chunk_overlap = 0
    fake_gemini.models.topics = {"salary": [1.0, 0.0]}
    fake_gemini.models.other = [0.0, 1.0]
    page = "Salary is paid on the 10th of every month.\nSalary slips are sent by email."
    upload(make_pdf([page]), "hr.pdf")
    fake_gemini.models.answer = GeminiAnswer(answer="On the 10th.", used_excerpts=[1, 2])

    response = ask(client, "When is the salary paid?")

    assert "[Excerpt 2 | hr.pdf, page 1]" in fake_gemini.models.generate_calls[0]
    assert [source["page"] for source in response.json()["sources"]] == [1]


# --- Invalid questions ---------------------------------------------------------


@pytest.mark.parametrize("body", [{"question": ""}, {"question": "   "}, {}])
def test_empty_question_is_rejected(client, fake_gemini, body):
    response = client.post("/chat", json=body)

    assert response.status_code == 422
    assert fake_gemini.models.embed_calls == []  # rejected before any work


# --- Gemini failures -----------------------------------------------------------


def test_chat_returns_429_when_llm_rate_limited(client, handbook_id, fake_gemini):
    fake_gemini.models.generate_errors = [
        ClientError(429, {"error": {"code": 429, "message": "Quota exceeded."}})
    ]

    response = ask(client, "Who founded Nimbus Robotics?")

    assert response.status_code == 429


def test_chat_returns_502_when_llm_fails(client, handbook_id, fake_gemini):
    fake_gemini.models.generate_errors = [
        ServerError(500, {"error": {"code": 500, "message": "Internal error"}})
    ]

    response = ask(client, "Who founded Nimbus Robotics?")

    assert response.status_code == 502
    assert response.json()["detail"] == "The AI service failed. Please try again."


def test_chat_retries_question_embedding_after_rate_limit(
    client, handbook_id, fake_gemini, no_sleep
):
    fake_gemini.models.embed_errors = [
        ClientError(429, {"error": {"code": 429, "message": "Please retry in 1s."}})
    ]

    response = ask(client, "Who founded Nimbus Robotics?")

    assert response.status_code == 200
    assert response.json()["found"] is True
    assert no_sleep == [2.0]
