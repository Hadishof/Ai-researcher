"""POST /chat: answer a question from the uploaded documents, with page citations."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from google import genai
from google.genai.errors import APIError

from app.core.config import Settings, get_settings
from app.core.gemini import get_gemini_client
from app.db.vector_store import VectorStore, get_vector_store
from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services.generation import generate_answer, is_not_found_answer, not_found_message
from app.services.retrieval import find_relevant_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    store: VectorStore = Depends(get_vector_store),
    client: genai.Client = Depends(get_gemini_client),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    question = request.question
    not_found = ChatResponse(answer=not_found_message(question), found=False, sources=[])

    try:
        # 1. Find the chunks that are close enough in meaning to the question.
        chunks = find_relevant_chunks(question, store, client, settings)
        if not chunks:
            return not_found  # nothing relevant: answer honestly, without calling the LLM

        # 2. Ask Gemini to answer using only those chunks.
        result = generate_answer(client, settings.generation_model, question, chunks)
    except APIError as error:
        if error.code == 429:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "The AI service's rate limit was reached. Please try again in a minute.",
            )
        logger.exception("Gemini request failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI service failed. Please try again.")

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
