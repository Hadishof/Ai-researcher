"""Asks Gemini to answer a question using only the retrieved document excerpts."""

import re

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.db.vector_store import SearchResult

HEBREW_LETTER = re.compile(r"[֐-׿]")

NOT_FOUND_ENGLISH = "I couldn't find this in the documents."
NOT_FOUND_HEBREW = "לא מצאתי את זה במסמכים."

SYSTEM_INSTRUCTION = """You are a document assistant.
Answer the user's question using ONLY the document excerpts you are given.
Do not use outside knowledge and do not guess.
Always answer in one or more complete sentences, in the same language as the question
(Hebrew or English), even for short facts.
For example, write "Support responds to critical problems within 4 hours."
and not "Response within 4 hours."
If excerpts from different documents disagree, do not combine them and do not choose one.
Say that the documents disagree, and state what each document says, naming each document.
In "used_excerpts", list the numbers of the excerpts your answer is based on,
including every excerpt you mention when documents disagree."""


class GeminiAnswer(BaseModel):
    """The JSON shape Gemini must reply with (structured output)."""

    answer: str
    used_excerpts: list[int]  # excerpt numbers from the prompt, e.g. [1, 3]


def is_hebrew(text: str) -> bool:
    return bool(HEBREW_LETTER.search(text))


def not_found_message(question: str) -> str:
    """The fixed 'not found' reply, in the language of the question."""
    return NOT_FOUND_HEBREW if is_hebrew(question) else NOT_FOUND_ENGLISH


def is_not_found_answer(answer: str, question: str) -> bool:
    """True if Gemini replied with the 'not found' sentence (or nothing at all)."""
    normalized = answer.strip().rstrip(".")
    return not normalized or normalized == not_found_message(question).rstrip(".")


def build_prompt(question: str, chunks: list[SearchResult], user_question: str) -> str:
    """
    Number each excerpt and label it with its file and page, then add the question.

    `question` is the one to answer: for a follow-up it is the standalone version
    written by the rewrite step. `user_question` is what the user really typed; the
    answer's language and the "not found" sentence follow it.
    """
    excerpts = "\n\n".join(
        f"[Excerpt {number} | {chunk.filename}, page {chunk.page}]\n{chunk.text}"
        for number, chunk in enumerate(chunks, 1)
    )
    follow_up = (
        f"(This question was rewritten from the user's follow-up question: \"{user_question}\". "
        f"Answer in the language of the follow-up question.)\n\n"
        if question != user_question
        else ""
    )
    return (
        f"Document excerpts:\n\n{excerpts}\n\n"
        f"Question: {question}\n\n"
        f"{follow_up}"
        f"If the excerpts do not contain the answer, set \"answer\" to exactly: "
        f"{not_found_message(user_question)} and set \"used_excerpts\" to an empty list."
    )


def generate_answer(
    client: genai.Client,
    model: str,
    question: str,
    chunks: list[SearchResult],
    user_question: str | None = None,
) -> GeminiAnswer:
    """Answer `question` from the chunks. `user_question` defaults to `question` (no rewrite)."""
    response = client.models.generate_content(
        model=model,
        contents=build_prompt(question, chunks, user_question or question),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0,  # same question -> same answer; no creativity needed for facts
            # Structured output: Gemini must reply with JSON matching GeminiAnswer,
            # and the SDK turns that JSON into a GeminiAnswer object for us.
            response_mime_type="application/json",
            response_schema=GeminiAnswer,
        ),
    )
    if isinstance(response.parsed, GeminiAnswer):
        return response.parsed
    # Empty or invalid reply: treat it as "no answer" (the caller returns "not found").
    return GeminiAnswer(answer="", used_excerpts=[])
