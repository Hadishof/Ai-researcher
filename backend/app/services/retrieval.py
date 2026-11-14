"""Turns text into Gemini embeddings and finds the chunks most relevant to a question."""

import re
import time

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from app.core.config import Settings
from app.db.vector_store import SearchResult, VectorStore

# Gemini accepts at most 100 texts per embedding request.
EMBED_BATCH_SIZE = 100

# The free tier allows a limited number of embeddings per minute. When we hit the
# limit, Gemini answers "429" and says how many seconds to wait. We wait and retry.
MAX_RETRIES = 3
RETRY_DELAY = re.compile(r"retry in ([\d.]+)s")


def _seconds_to_wait(error: ClientError) -> float:
    match = RETRY_DELAY.search(str(error))
    seconds = float(match.group(1)) + 1 if match else 30
    return min(seconds, 60)


def _embed_batch(
    client: genai.Client, batch: list[str], model: str, task_type: str
) -> list[list[float]]:
    retries = 0
    while True:
        try:
            response = client.models.embed_content(
                model=model,
                contents=batch,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            return [embedding.values for embedding in response.embeddings]
        except ClientError as error:
            if error.code != 429 or retries == MAX_RETRIES:
                raise
            retries += 1
            time.sleep(_seconds_to_wait(error))


def embed_texts(
    client: genai.Client,
    texts: list[str],
    model: str,
    task_type: str,
) -> list[list[float]]:
    """
    Turn each text into a list of numbers (an embedding) that captures its meaning.

    task_type tells Gemini how the text will be used:
    "RETRIEVAL_DOCUMENT" for chunks we store, "RETRIEVAL_QUERY" for questions.
    Gemini tunes each embedding for its role, which improves search quality.
    """
    embeddings = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        embeddings.extend(_embed_batch(client, batch, model, task_type))
    return embeddings


def find_relevant_chunks(
    question: str,
    store: VectorStore,
    client: genai.Client,
    settings: Settings,
) -> list[SearchResult]:
    """Return the closest chunks to the question, dropping any that are not close enough."""
    query_embedding = embed_texts(
        client, [question], model=settings.embedding_model, task_type="RETRIEVAL_QUERY"
    )[0]
    results = store.search(query_embedding, top_k=settings.top_k)
    return [result for result in results if result.distance <= settings.max_distance]
