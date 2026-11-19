"""Tests for loading settings: the clear errors shown when the server can't start."""

import pytest

from app.core.config import Settings, get_settings


@pytest.fixture
def fresh_settings(monkeypatch):
    """
    Let a test load settings from scratch, using only the environment variables it sets.

    - get_settings() remembers its first result (lru_cache), so we clear that memory.
    - Settings normally also reads backend/.env; we turn that off, so your real
      API key can't affect the test.
    monkeypatch puts everything back after the test.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_missing_api_key_gives_a_clear_error(fresh_settings):
    fresh_settings.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as error:
        get_settings()

    assert str(error.value) == (
        "GOOGLE_API_KEY is missing. Copy backend/.env.example to backend/.env "
        "and put your Gemini API key in it."
    )


def test_overlap_not_smaller_than_chunk_size_is_rejected(fresh_settings):
    fresh_settings.setenv("GOOGLE_API_KEY", "secret-test-key")
    fresh_settings.setenv("CHUNK_SIZE", "500")
    fresh_settings.setenv("CHUNK_OVERLAP", "500")  # must be smaller than CHUNK_SIZE

    with pytest.raises(RuntimeError) as error:
        get_settings()

    message = str(error.value)
    assert message.startswith("Invalid settings:")
    assert "CHUNK_OVERLAP must be smaller than CHUNK_SIZE." in message
    # The error message must never reveal the API key.
    assert "secret-test-key" not in message
