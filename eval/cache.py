"""
Disk caches for Gemini results, so re-running the evaluation costs no API calls.

- EmbeddingCache: eval/.cache/embeddings/, one file per embedded text. The file name
  is a SHA-256 hash of (model, task type, text): the same text with the same model
  and task always maps to the same file, and any change to one of them gives a
  different file, so a stale embedding is never reused.
- GenerationCache: eval/.cache/generations/, one file per answer or rewrite, keyed
  by a hash of the whole request (see cached_client.generation_key).
"""

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / ".cache"


def cache_key(*parts: str) -> str:
    """One hash for several strings. The separator stops ("ab", "c") and ("a", "bc") colliding."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


class EmbeddingCache:
    def __init__(self, model: str, folder: Path = CACHE_DIR / "embeddings"):
        self.model = model
        self.folder = folder

    def _path(self, text: str, task_type: str) -> Path:
        return self.folder / f"{cache_key(self.model, task_type, text)}.json"

    def get(self, text: str, task_type: str) -> list[float] | None:
        path = self._path(text, task_type)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def has(self, text: str, task_type: str) -> bool:
        return self._path(text, task_type).exists()

    def put(self, text: str, task_type: str, embedding: list[float]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._path(text, task_type).write_text(json.dumps(embedding), encoding="utf-8")


class GenerationCache:
    """Gemini's text replies (answers and follow-up rewrites), stored by request key."""

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
