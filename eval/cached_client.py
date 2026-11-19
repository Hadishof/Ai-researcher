"""
A stand-in for the Gemini client that caches answers on disk, paces requests and retries.

The app's functions (rewrite_question, answer_from_chunks) receive the Gemini
client as a parameter. The evaluation passes this wrapper instead, so it runs
the app's exact code, while:
- an identical request is answered from eval/.cache/generations/ (no API call),
  so a run that stops halfway resumes where it stopped;
- real requests are spaced at least `pace_seconds` apart (free-tier rate limits);
- a rate-limit (429) or a temporary server error (5xx) is retried after a wait.

The cache key is a hash of everything Gemini sees: model, system instruction,
settings and the full prompt (which includes the question and every excerpt).
Change any of them, for example the chunk size, and the key changes too.
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import ValidationError

from app.services.retrieval import MAX_RETRIES, seconds_to_wait
from cache import CACHE_DIR, cache_key

SERVER_ERROR_WAIT = 30  # seconds to wait after a 5xx error (Gemini overloaded)


class DailyLimitReached(Exception):
    """The free tier's requests-per-day limit is used up. It resets the next day."""


def is_daily_limit(error: APIError) -> bool:
    """
    A 429 can mean "too many per minute" (wait and retry) or "too many today"
    (stop). Gemini names the quota in the error, e.g.
    "GenerateRequestsPerDayPerProjectPerModel-FreeTier" for the daily one.
    """
    return error.code == 429 and "PerDay" in str(error)


def generation_key(model: str, contents: str, config: types.GenerateContentConfig) -> str:
    schema = getattr(config.response_schema, "__name__", "") if config.response_schema else ""
    return cache_key(
        model,
        str(config.system_instruction or ""),
        str(config.temperature),
        str(config.response_mime_type or ""),
        schema,
        contents,
    )


class GenerationCache:
    def __init__(self, folder: Path = CACHE_DIR / "generations"):
        self.folder = folder

    def _path(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    def has(self, key: str) -> bool:
        return self._path(key).exists()

    def get(self, key: str) -> str | None:
        path = self._path(key)
        return json.loads(path.read_text(encoding="utf-8"))["text"] if path.exists() else None

    def put(self, key: str, text: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")


def make_response(text: str, config: types.GenerateContentConfig) -> SimpleNamespace:
    """
    Rebuild what the app reads from a Gemini response: `.text`, and `.parsed`
    for structured output (the JSON text turned back into the Pydantic object).
    """
    parsed = None
    if config.response_schema is not None:
        try:
            parsed = config.response_schema.model_validate_json(text)
        except ValidationError:
            parsed = None  # invalid JSON: the app treats it as "no answer"
    return SimpleNamespace(text=text, parsed=parsed)


class _CachedModels:
    def __init__(self, client: genai.Client, cache: GenerationCache, pace_seconds: float):
        self._client = client
        self._cache = cache
        self._pace_seconds = pace_seconds
        self._last_request = 0.0
        self.calls = 0  # real API calls made (cache hits are not counted)

    def generate_content(self, model: str, contents: str, config: types.GenerateContentConfig):
        key = generation_key(model, contents, config)
        cached = self._cache.get(key)
        if cached is not None:
            return make_response(cached, config)

        text = self._call_with_retries(model, contents, config)
        if text:  # an empty reply may be a passing glitch: don't keep it, ask again next run
            self._cache.put(key, text)
        return make_response(text, config)

    def _call_with_retries(self, model: str, contents: str, config) -> str:
        retries = 0
        while True:
            wait = self._last_request + self._pace_seconds - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            try:
                response = self._client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                self.calls += 1
                return response.text or ""
            except APIError as error:
                if is_daily_limit(error):
                    # Waiting a minute cannot help when the limit resets tomorrow: stop now.
                    raise DailyLimitReached() from error
                temporary = error.code == 429 or (error.code or 0) >= 500
                if not temporary or retries == MAX_RETRIES:
                    raise
                retries += 1
                delay = seconds_to_wait(error) if error.code == 429 else SERVER_ERROR_WAIT
                print(f"    Gemini error {error.code}; waiting {delay:.0f}s (retry {retries}/{MAX_RETRIES})")
                time.sleep(delay)


class CachedGeminiClient:
    """Has the same `client.models.generate_content(...)` shape the app uses."""

    def __init__(self, client: genai.Client, cache: GenerationCache, pace_seconds: float):
        self.models = _CachedModels(client, cache, pace_seconds)
