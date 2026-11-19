"""Turns a follow-up question into a standalone question, so the document search can understand it."""

from google import genai
from google.genai import types

from app.db.conversation_store import Message

REWRITE_INSTRUCTION = """You rewrite follow-up questions for a document search engine.
You get the end of a conversation and the user's latest question.
Rewrite the latest question so it can be understood on its own, without the conversation:
replace words like "it", "that" or "the second one" with what they refer to.
Do not answer the question. Do not add facts that are not in the conversation.
Keep the same language as the latest question.
If the latest question is already clear on its own, return it unchanged.
Reply with the rewritten question only."""


def build_rewrite_prompt(history: list[Message], question: str) -> str:
    lines = [
        f"{'User' if message.role == 'user' else 'Assistant'}: {message.content}"
        for message in history
    ]
    conversation = "\n".join(lines)
    return f"Conversation:\n{conversation}\n\nLatest question: {question}"


def rewrite_question(
    client: genai.Client,
    model: str,
    history: list[Message],
    question: str,
) -> str:
    """
    Example: after "How many vacation days do employees get?", the follow-up
    "and sick days?" becomes "How many sick days do employees get?".
    If Gemini returns nothing, the original question is used.
    """
    response = client.models.generate_content(
        model=model,
        contents=build_rewrite_prompt(history, question),
        config=types.GenerateContentConfig(
            system_instruction=REWRITE_INSTRUCTION,
            temperature=0,  # the same conversation always gives the same rewrite
        ),
    )
    rewritten = (response.text or "").strip()
    return rewritten or question
