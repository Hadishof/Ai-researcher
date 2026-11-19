"""POST /chat: answer a question from the conversation's documents, and save both messages."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from google import genai
from google.genai.errors import APIError

from app.core.config import Settings, get_settings
from app.core.gemini import get_gemini_client
from app.db.conversation_store import ConversationStore, get_conversation_store
from app.db.vector_store import VectorStore, get_vector_store
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.answering import answer_question
from app.services.rewriting import rewrite_question
from app.services.titles import make_title

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


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
