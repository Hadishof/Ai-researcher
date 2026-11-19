"""
Answers a question from the selected documents: search, then generate, then pick the sources.

Used by POST /chat, and by the evaluation (eval/), which runs answer_from_chunks
on its own search results so it measures exactly what the app does.
"""

from google import genai

from app.core.config import Settings
from app.db.vector_store import SearchResult, VectorStore
from app.schemas.chat import ChatResponse, Source
from app.services.generation import generate_answer, is_not_found_answer, not_found_message
from app.services.retrieval import find_relevant_chunks


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
    # Find the chunks of the selected documents that are close enough in meaning.
    chunks = find_relevant_chunks(search_question, document_ids, store, client, settings)
    return answer_from_chunks(question, search_question, chunks, client, settings)


def answer_from_chunks(
    question: str,
    search_question: str,
    chunks: list[SearchResult],
    client: genai.Client,
    settings: Settings,
) -> ChatResponse:
    """
    Turn the chunks found by the search into the final response.

    A separate function so the evaluation runs exactly the same steps as the app
    on its own search results.
    """
    not_found = ChatResponse(answer=not_found_message(question), found=False, sources=[])

    # 1. No chunk close enough: answer honestly, without calling the LLM.
    if not chunks:
        return not_found

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
