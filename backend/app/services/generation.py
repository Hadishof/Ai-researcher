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
In "used_excerpts", list the numbers of the excerpts your answer is based on."""


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


def build_prompt(question: str, chunks: list[SearchResult]) -> str:
    """Number each excerpt and label it with its file and page, then add the question."""
    excerpts = "\n\n".join(
        f"[Excerpt {number} | {chunk.filename}, page {chunk.page}]\n{chunk.text}"
        for number, chunk in enumerate(chunks, 1)
    )
    return (
        f"Document excerpts:\n\n{excerpts}\n\n"
        f"Question: {question}\n\n"
        f"If the excerpts do not contain the answer, set \"answer\" to exactly: "
        f"{not_found_message(question)} and set \"used_excerpts\" to an empty list."
    )


def generate_answer(
    client: genai.Client,
    model: str,
    question: str,
    chunks: list[SearchResult],
) -> GeminiAnswer:
    response = client.models.generate_content(
        model=model,
        contents=build_prompt(question, chunks),
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
