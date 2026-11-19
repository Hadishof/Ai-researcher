"""
Fetches the embeddings the evaluation needs, through the disk cache, with pacing.

The work is split in two steps so the cost is known before anything is spent:
1. plan():  find which texts are not cached yet (free, no API call)
2. fetch(): embed only those, in batches, waiting between requests

--dry-run stops after step 1, so the number it prints is exactly what step 2 sends.
"""

import math
import time

from google import genai

from app.services.retrieval import EMBED_BATCH_SIZE, embed_texts
from cache import EmbeddingCache

# Embedding requests are sent with this task type for stored chunks and for questions.
DOCUMENT = "RETRIEVAL_DOCUMENT"
QUERY = "RETRIEVAL_QUERY"


class PacedEmbedder:
    def __init__(self, cache: EmbeddingCache, pace_seconds: float):
        self.cache = cache
        self.pace_seconds = pace_seconds
        self._last_request = 0.0

    def plan(self, texts_by_task: dict[str, list[str]]) -> dict[str, list[str]]:
        """The texts still missing from the cache, per task type, without duplicates."""
        missing = {}
        for task_type, texts in texts_by_task.items():
            unique = list(dict.fromkeys(texts))  # removes duplicates, keeps the order
            missing[task_type] = [t for t in unique if not self.cache.has(t, task_type)]
        return missing

    @staticmethod
    def count_requests(missing: dict[str, list[str]]) -> int:
        """One request per batch of up to 100 texts, per task type."""
        return sum(math.ceil(len(texts) / EMBED_BATCH_SIZE) for texts in missing.values())

    def _wait_for_pace(self) -> None:
        """Leave at least `pace_seconds` between two requests, to stay under the rate limit."""
        wait = self._last_request + self.pace_seconds - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def fetch(self, client: genai.Client, missing: dict[str, list[str]]) -> None:
        """
        Embed the missing texts and save each one in the cache right away.

        Saving after every batch means a crash loses at most one batch: the next
        run plans again and only fetches what is still missing. A rate-limit
        error (429) is retried by the backend's embed_texts.
        """
        total = self.count_requests(missing)
        done = 0
        for task_type, texts in missing.items():
            for start in range(0, len(texts), EMBED_BATCH_SIZE):
                batch = texts[start : start + EMBED_BATCH_SIZE]
                self._wait_for_pace()
                embeddings = embed_texts(client, batch, self.cache.model, task_type)
                for text, embedding in zip(batch, embeddings):
                    self.cache.put(text, task_type, embedding)
                done += 1
                print(f"  embedding request {done}/{total}: {len(batch)} {task_type} texts")
