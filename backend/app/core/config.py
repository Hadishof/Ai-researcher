"""All app settings in one place, read from environment variables or backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ folder (this file is backend/app/core/config.py)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required: the app refuses to start without it.
    google_api_key: str = Field(min_length=1)

    # Gemini models
    embedding_model: str = "gemini-embedding-001"
    generation_model: str = "gemini-2.5-flash"

    # Vector database
    chroma_path: Path = BACKEND_DIR / "chroma_db"
    collection_name: str = "documents"

    # Saved conversations (SQLite). The folder is created automatically.
    database_path: Path = BACKEND_DIR / "data" / "conversations.db"
    # How many earlier messages are sent to Gemini when rewriting a follow-up question
    # into a standalone one. 0 turns the rewrite off.
    history_messages: int = Field(default=6, ge=0)

    # The defaults below for chunk size, MAX_DISTANCE and RELATIVE_MARGIN were chosen by
    # fixed rules on the evaluation's dev set. Evidence:
    # eval/results/2026-11-19_225052_retrieval.md

    # Chunking: the size and overlap of each text piece, in characters.
    # 500 had the best ranking (MRR) on the dev set. Overlap stays 15% of the size.
    chunk_size: int = Field(default=500, gt=0)
    chunk_overlap: int = Field(default=75, ge=0)

    # Retrieval
    top_k: int = Field(default=5, gt=0)
    # Cosine distance: 0 = same meaning, 1 = unrelated, 2 = opposite.
    # Chunks farther than this from the question are treated as not relevant.
    # Fragile: 0.34 vs 0.38 was decided by a single dev question. The filter only
    # blocks clearly unrelated questions; "not found" questions close to the
    # documents' topics get through, and the LLM has to answer "not found" itself.
    max_distance: float = Field(default=0.34, ge=0, le=2)
    # A chunk is also dropped if it is more than this much farther than the best chunk.
    # This removes "somewhat related" pages when one page clearly matches best.
    # 0.10 is the smallest margin that kept every correct page, and both pages of
    # every conflict question (so the LLM can report both sides), on the dev set.
    relative_margin: float = Field(default=0.10, ge=0, le=2)

    # Uploads
    max_upload_mb: int = Field(default=20, gt=0)

    # CORS: the only website address allowed to call this API
    frontend_origin: str = "http://localhost:5173"

    # Logging: set LOG_LEVEL=DEBUG to see retrieval distances while testing
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def check_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Load settings once and reuse them. Stops with a clear message if the API key is missing."""
    try:
        return Settings()
    except ValidationError as error:
        problems = error.errors(include_input=False)  # never print values: they include the API key
        if any(problem["loc"] == ("google_api_key",) for problem in problems):
            raise RuntimeError(
                "GOOGLE_API_KEY is missing. Copy backend/.env.example to backend/.env "
                "and put your Gemini API key in it."
            ) from None
        details = "; ".join(problem["msg"] for problem in problems)
        raise RuntimeError(f"Invalid settings: {details}") from None
