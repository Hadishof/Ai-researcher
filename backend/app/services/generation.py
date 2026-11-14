"""Asks Gemini to answer a question using only the retrieved document excerpts."""

import re

from google import genai
from google.genai import types

from app.db.vector_store import SearchResult

HEBREW_LETTER = re.compile(r"[֐-׿]")

NOT_FOUND_ENGLISH = "I couldn't find this in the documents."
NOT_FOUND_HEBREW = "לא מצאתי את זה במסמכים."

SYSTEM_INSTRUCTION = """You are a document assistant.
Answer the user's question using ONLY the document excerpts you are given.
Do not use outside knowledge and do not guess.
Answer in the same language as the question (Hebrew or English).
Keep the answer clear and concise."""


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
    """Label each excerpt with its file and page, then add the question."""
    excerpts = "\n\n".join(
        f"[Excerpt {number} | {chunk.filename}, page {chunk.page}]\n{chunk.text}"
        for number, chunk in enumerate(chunks, 1)
    )
    return (
        f"Document excerpts:\n\n{excerpts}\n\n"
        f"Question: {question}\n\n"
        f"If the excerpts do not contain the answer, reply with exactly: "
        f"{not_found_message(question)}"
    )


def generate_answer(
    client: genai.Client,
    model: str,
    question: str,
    chunks: list[SearchResult],
) -> str:
    response = client.models.generate_content(
        model=model,
        contents=build_prompt(question, chunks),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0,  # same question -> same answer; no creativity needed for facts
        ),
    )
    return (response.text or "").strip()
