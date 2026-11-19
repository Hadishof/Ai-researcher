"""One shared Gemini client, used for both embeddings and answers, and its rate-limit helpers."""

import re
from functools import lru_cache

from google import genai
from google.genai.errors import APIError

from app.core.config import get_settings

# The free tier allows a limited number of requests per minute. When we hit the
# limit, Gemini answers "429" and says how many seconds to wait. We wait and retry.
MAX_RETRIES = 3
RETRY_DELAY = re.compile(r"retry in ([\d.]+)s")


def seconds_to_wait(error: APIError) -> float:
    """How long to wait after a 429: the time Gemini asks for plus 1 second, at most 60."""
    match = RETRY_DELAY.search(str(error))
    seconds = float(match.group(1)) + 1 if match else 30
    return min(seconds, 60)


@lru_cache
def get_gemini_client() -> genai.Client:
    return genai.Client(api_key=get_settings().google_api_key)
