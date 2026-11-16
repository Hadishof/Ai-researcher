"""
Tests for POST /chat: retrieval filters, sources, 'not found', Gemini failures,
saving messages, follow-up questions, and searching only the chat's own documents.
"""

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
    """Ask in a new conversation that has every uploaded document selected."""
    documents = client.get("/documents").json()["documents"]
    conversation = client.post(
        "/conversations", json={"document_ids": [d["document_id"] for d in documents]}
    ).json()
    return client.post("/chat", json={"conversation_id": conversation["id"], "question": question})


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


def test_400_when_no_documents_are_uploaded(client, fake_gemini):
    # With no documents, the conversation has none selected, so there is nothing to search.
    response = ask(client, "Who founded Nimbus Robotics?")

    assert response.status_code == 400
    assert fake_gemini.models.embed_calls == []
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


# --- Saving messages -----------------------------------------------------------


def test_question_and_answer_are_saved(client, handbook_id, fake_gemini, new_conversation, ask_in):
    fake_gemini.models.answer = GeminiAnswer(
        answer="Nimbus Robotics was founded by Dana Levi.", used_excerpts=[1]
    )
    conversation_id = new_conversation([handbook_id])

    ask_in(conversation_id, "Who founded Nimbus Robotics?")

    saved = client.get(f"/conversations/{conversation_id}").json()
    assert saved["title"] == "Who founded Nimbus Robotics?"  # set from the first question
    user, assistant = saved["messages"]
    assert user["role"] == "user"
    assert user["content"] == "Who founded Nimbus Robotics?"
    assert user["found"] is None
    assert user["sources"] == []
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Nimbus Robotics was founded by Dana Levi."
    assert assistant["found"] is True
    assert assistant["sources"] == [
        {
            "document_id": handbook_id,
            "filename": "handbook.pdf",
            "page": 1,
            "score": 1.0,
            "document_deleted": False,
        }
    ]


def test_not_found_answer_is_saved_too(client, handbook_id, new_conversation, ask_in):
    conversation_id = new_conversation([handbook_id])

    ask_in(conversation_id, "What is the weather today?")

    assistant = client.get(f"/conversations/{conversation_id}").json()["messages"][1]
    assert assistant["content"] == "I couldn't find this in the documents."
    assert assistant["found"] is False


def test_nothing_is_saved_when_gemini_fails(
    client, handbook_id, fake_gemini, new_conversation, ask_in
):
    conversation_id = new_conversation([handbook_id])
    fake_gemini.models.generate_errors = [
        ServerError(500, {"error": {"code": 500, "message": "Internal error"}})
    ]

    response = ask_in(conversation_id, "Who founded Nimbus Robotics?")

    assert response.status_code == 502
    saved = client.get(f"/conversations/{conversation_id}").json()
    assert saved["messages"] == []  # no unanswered question is left behind
    assert saved["title"] is None


def test_long_first_question_gives_a_short_title(client, handbook_id, new_conversation, ask_in):
    conversation_id = new_conversation([handbook_id])
    question = "Who founded Nimbus Robotics and in which year did the company start selling arms?"

    ask_in(conversation_id, question)

    title = client.get(f"/conversations/{conversation_id}").json()["title"]
    assert title == "Who founded Nimbus Robotics and in which year did the…"  # cut at a word


def test_title_comes_only_from_the_first_question(client, handbook_id, new_conversation, ask_in):
    conversation_id = new_conversation([handbook_id])

    ask_in(conversation_id, "Who founded Nimbus Robotics?")
    ask_in(conversation_id, "How fast does support respond?")

    title = client.get(f"/conversations/{conversation_id}").json()["title"]
    assert title == "Who founded Nimbus Robotics?"


def test_renamed_title_is_not_replaced(client, handbook_id, new_conversation, ask_in):
    conversation_id = new_conversation([handbook_id])
    client.patch(f"/conversations/{conversation_id}", json={"title": "Company facts"})

    ask_in(conversation_id, "Who founded Nimbus Robotics?")

    assert client.get(f"/conversations/{conversation_id}").json()["title"] == "Company facts"


def test_chat_in_unknown_conversation_returns_404(client, fake_gemini):
    response = client.post("/chat", json={"conversation_id": 999, "question": "Hello?"})

    assert response.status_code == 404
    assert fake_gemini.models.embed_calls == []


# --- Follow-up questions (rewritten before searching) --------------------------


def test_first_message_is_not_rewritten(client, handbook_id, fake_gemini, new_conversation, ask_in):
    conversation_id = new_conversation([handbook_id])

    ask_in(conversation_id, "Who founded Nimbus Robotics?")

    assert fake_gemini.models.rewrite_calls == []
    assert fake_gemini.models.embed_calls[-1] == ["Who founded Nimbus Robotics?"]


def test_follow_up_is_rewritten_and_the_rewrite_is_searched(
    client, handbook_id, fake_gemini, new_conversation, ask_in
):
    conversation_id = new_conversation([handbook_id])
    fake_gemini.models.answer = GeminiAnswer(
        answer="Nimbus Robotics was founded by Dana Levi.", used_excerpts=[1]
    )
    ask_in(conversation_id, "Who founded Nimbus Robotics?")

    fake_gemini.models.rewritten = "How fast does Nimbus Robotics support respond?"
    fake_gemini.models.answer = GeminiAnswer(
        answer="Support responds to critical problems within 4 hours.", used_excerpts=[1]
    )
    response = ask_in(conversation_id, "And their support?")

    # 1. Gemini was asked to rewrite, and saw the earlier messages and the new question.
    [rewrite_prompt] = fake_gemini.models.rewrite_calls
    assert "User: Who founded Nimbus Robotics?" in rewrite_prompt
    assert "Assistant: Nimbus Robotics was founded by Dana Levi." in rewrite_prompt
    assert "Latest question: And their support?" in rewrite_prompt
    # 2. The search used the rewritten question, not "And their support?".
    assert fake_gemini.models.embed_calls[-1] == ["How fast does Nimbus Robotics support respond?"]
    # 3. The answer prompt has the standalone question and mentions the original follow-up.
    answer_prompt = fake_gemini.models.generate_calls[-1]
    assert "Question: How fast does Nimbus Robotics support respond?" in answer_prompt
    assert '"And their support?"' in answer_prompt
    assert response.json()["sources"][0]["page"] == 2
    # 4. What is saved is what the user really typed.
    messages = client.get(f"/conversations/{conversation_id}").json()["messages"]
    assert messages[2]["content"] == "And their support?"


def test_empty_rewrite_falls_back_to_the_original_question(
    client, handbook_id, fake_gemini, new_conversation, ask_in
):
    conversation_id = new_conversation([handbook_id])
    ask_in(conversation_id, "Who founded Nimbus Robotics?")
    fake_gemini.models.rewritten = "   "  # Gemini returned nothing useful

    ask_in(conversation_id, "How fast does support respond?")

    assert len(fake_gemini.models.rewrite_calls) == 1
    assert fake_gemini.models.embed_calls[-1] == ["How fast does support respond?"]


def test_rewrite_sees_only_the_last_few_messages(
    client, handbook_id, fake_gemini, settings, new_conversation, ask_in
):
    settings.history_messages = 2  # only the last question and its answer
    conversation_id = new_conversation([handbook_id])
    ask_in(conversation_id, "Who founded Nimbus Robotics?")
    ask_in(conversation_id, "How fast does support respond?")

    ask_in(conversation_id, "And the robot arm?")

    last_rewrite_prompt = fake_gemini.models.rewrite_calls[-1]
    assert "How fast does support respond?" in last_rewrite_prompt
    assert "Who founded Nimbus Robotics?" not in last_rewrite_prompt


def test_rewrite_is_off_when_history_messages_is_zero(
    client, handbook_id, fake_gemini, settings, new_conversation, ask_in
):
    settings.history_messages = 0
    conversation_id = new_conversation([handbook_id])
    ask_in(conversation_id, "Who founded Nimbus Robotics?")

    ask_in(conversation_id, "How fast does support respond?")

    assert fake_gemini.models.rewrite_calls == []


# --- Each conversation searches only its own documents -------------------------

POLICY_2023 = ["Support responds to critical problems within 4 hours."]
POLICY_2024 = ["Support responds to critical problems within 24 hours."]


@pytest.fixture
def two_policies(upload, make_pdf) -> tuple[str, str]:
    """Two documents that disagree about the same fact. Both match "support" equally well."""
    first = upload(make_pdf(POLICY_2023), "policy-2023.pdf").json()["document_id"]
    second = upload(make_pdf(POLICY_2024), "policy-2024.pdf").json()["document_id"]
    return first, second


def test_each_chat_searches_only_its_own_document(
    client, two_policies, fake_gemini, new_conversation, ask_in
):
    old_policy, new_policy = two_policies
    chat_a = new_conversation([old_policy])
    chat_b = new_conversation([new_policy])

    answer_a = ask_in(chat_a, "How fast does support respond?").json()
    prompt_a = fake_gemini.models.generate_calls[-1]
    answer_b = ask_in(chat_b, "How fast does support respond?").json()
    prompt_b = fake_gemini.models.generate_calls[-1]

    assert "within 4 hours" in prompt_a
    assert "within 24 hours" not in prompt_a
    assert "within 24 hours" in prompt_b
    assert "within 4 hours" not in prompt_b
    assert [s["document_id"] for s in answer_a["sources"]] == [old_policy]
    assert [s["document_id"] for s in answer_b["sources"]] == [new_policy]


def test_conflicting_documents_are_both_sent_with_the_conflict_rule(
    client, two_policies, fake_gemini, new_conversation, ask_in
):
    old_policy, new_policy = two_policies
    conversation_id = new_conversation([old_policy, new_policy])
    fake_gemini.models.answer = GeminiAnswer(
        answer="The documents disagree: policy-2023.pdf says 4 hours, "
        "policy-2024.pdf says 24 hours.",
        used_excerpts=[1, 2],
    )

    response = ask_in(conversation_id, "How fast does support respond?")

    prompt = fake_gemini.models.generate_calls[-1]
    assert "policy-2023.pdf, page 1]" in prompt
    assert "policy-2024.pdf, page 1]" in prompt
    assert "documents disagree" in fake_gemini.models.last_config.system_instruction
    # Both documents are cited, so the user can check each one.
    assert {s["document_id"] for s in response.json()["sources"]} == {old_policy, new_policy}


def test_400_when_the_conversation_has_no_documents_selected(
    client, handbook_id, fake_gemini, new_conversation, ask_in
):
    conversation_id = new_conversation([])  # a document exists, but none is selected
    embed_calls_before = len(fake_gemini.models.embed_calls)  # the upload's embedding

    response = ask_in(conversation_id, "Who founded Nimbus Robotics?")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Select at least one document for this chat before asking."
    )
    assert len(fake_gemini.models.embed_calls) == embed_calls_before  # Gemini was not called
    assert fake_gemini.models.generate_calls == []
    assert client.get(f"/conversations/{conversation_id}").json()["messages"] == []
