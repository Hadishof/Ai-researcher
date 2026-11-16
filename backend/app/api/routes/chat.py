"""POST /chat: answer a question from the conversation's documents, and save both messages."""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from google import genai
from google.genai.errors import APIError

from app.core.config import Settings, get_settings
from app.core.gemini import get_gemini_client
from app.db.conversation_store import ConversationStore, get_conversation_store
from app.db.vector_store import VectorStore, get_vector_store
from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services.generation import generate_answer, is_not_found_answer, not_found_message
from app.services.retrieval import find_relevant_chunks
from app.services.rewriting import rewrite_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

TITLE_MAX_LENGTH = 60
WHITESPACE = re.compile(r"\s+")


def make_title(question: str) -> str:
    """A short conversation title from the first question, cut at a whole word."""
    title = WHITESPACE.sub(" ", question).strip()
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    cut = title.rfind(" ", 0, TITLE_MAX_LENGTH)
    if cut <= TITLE_MAX_LENGTH // 2:  # no space in a sensible place: cut at the limit
        cut = TITLE_MAX_LENGTH
    return title[:cut].rstrip() + "…"


def answer_question(
    question: str,
    search_question: str,
    document_ids: list[str],
    store: VectorStore,
    client: genai.Client,
    settings: Settings,
) -> ChatResponse:
    """
    Search the selected documents with `search_question` and answer from what was found.

    `question` is what the user typed; `search_question` is the standalone version
    (the same text for a first message, a rewritten one for a follow-up).
    """
    not_found = ChatResponse(answer=not_found_message(question), found=False, sources=[])

    # 1. Find the chunks of the selected documents that are close enough in meaning.
    chunks = find_relevant_chunks(search_question, document_ids, store, client, settings)
    if not chunks:
        return not_found  # nothing relevant: answer honestly, without calling the LLM

    # 2. Ask Gemini to answer using only those chunks.
    result = generate_answer(
        client, settings.generation_model, search_question, chunks, user_question=question
    )
    if is_not_found_answer(result.answer, question):
        return not_found

    # 3. Keep only the excerpts Gemini says it used. Excerpts are numbered from 1
    #    in the prompt; numbers that don't match a real excerpt are ignored.
    used_chunks = [
        chunk for number, chunk in enumerate(chunks, 1) if number in result.used_excerpts
    ]
    if not used_chunks:
        return not_found  # an answer that cites no excerpt is not backed by the documents

    # 4. One source per (document, page), closest first. Chunks are already sorted
    #    closest first, so the first chunk seen for a page has that page's best score.
    sources: list[Source] = []
    seen = set()
    for chunk in used_chunks:
        key = (chunk.document_id, chunk.page)
        if key not in seen:
            seen.add(key)
            sources.append(
                Source(
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page=chunk.page,
                    score=round(1 - chunk.distance, 2),
                )
            )

    return ChatResponse(answer=result.answer, found=True, sources=sources)


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    store: VectorStore = Depends(get_vector_store),
    conversations: ConversationStore = Depends(get_conversation_store),
    client: genai.Client = Depends(get_gemini_client),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    conversation = conversations.get_conversation(request.conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")

    # Each conversation searches only its own documents. Without any, there is nothing
    # to answer from, so stop before calling Gemini.
    document_ids = conversations.get_document_ids(conversation.id)
    if not document_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Select at least one document for this chat before asking.",
        )

    question = request.question
    history = conversations.recent_messages(conversation.id, settings.history_messages)

    try:
        # A follow-up like "and in Hebrew?" means nothing to a search on its own, so
        # Gemini first rewrites it into a standalone question. Skipped for the first message.
        if history:
            search_question = rewrite_question(
                client, settings.generation_model, history, question
            )
            logger.debug("Rewrote %r -> %r", question, search_question)
        else:
            search_question = question

        response = answer_question(
            question, search_question, document_ids, store, client, settings
        )
    except APIError as error:
        # Nothing is saved when Gemini fails, so the user can simply ask again.
        if error.code == 429:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "The AI service's rate limit was reached. Please try again in a minute.",
            )
        logger.exception("Gemini request failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI service failed. Please try again.")

    conversations.add_exchange(
        conversation.id,
        question=question,
        answer=response.answer,
        found=response.found,
        sources=[source.model_dump() for source in response.sources],
        title=make_title(question),
    )
    return response
