"""
Shared test setup (fixtures). pytest loads this file automatically.

Every test gets:
- a fake Gemini client (no real API calls, no API key, no internet)
- an empty ChromaDB in a temporary folder (your real data is never touched)
- an empty SQLite conversations database in the same temporary folder
- test settings that ignore your backend/.env file
"""

import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

# main.py loads the settings when it is imported, and the settings require an API key.
# Set a fake one BEFORE importing the app, so tests work on a machine with no .env file.
os.environ.setdefault("GOOGLE_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.gemini import get_gemini_client  # noqa: E402
from app.db.conversation_store import ConversationStore, get_conversation_store  # noqa: E402
from app.db.vector_store import VectorStore, get_vector_store  # noqa: E402
from app.main import app  # noqa: E402
from app.services.generation import GeminiAnswer, is_hebrew  # noqa: E402

FONT_PATH = Path(__file__).parent / "fonts" / "Alef-Regular.ttf"
pdfmetrics.registerFont(TTFont("Alef", str(FONT_PATH)))


# ---------------------------------------------------------------------------
# Fake Gemini
# ---------------------------------------------------------------------------

# Each topic points in its own direction, so texts about different topics are
# unrelated (cosine distance 1) and texts about the same topic are identical (distance 0).
DEFAULT_TOPICS = {
    "founded": [1.0, 0.0, 0.0, 0.0, 0.0],
    "support": [0.0, 1.0, 0.0, 0.0, 0.0],
    "חופשה": [0.0, 0.0, 1.0, 0.0, 0.0],  # "vacation"
    "load": [0.0, 0.0, 0.0, 1.0, 0.0],
}
# Text that matches no topic gets this direction (unrelated to every topic).
OTHER = [0.0, 0.0, 0.0, 0.0, 1.0]


class FakeModels:
    """
    Stands in for `client.models`: the two methods our code calls.

    generate_content is used for two different jobs, told apart by the request:
    - answering: asks for JSON (a response_schema), so it returns `answer`
    - rewriting a follow-up question: asks for plain text, so it returns `rewritten`
    """

    def __init__(self) -> None:
        # Keyword -> embedding. The first keyword found in a text decides its embedding.
        self.topics: dict[str, list[float]] = dict(DEFAULT_TOPICS)
        self.other: list[float] = OTHER
        # What generate_content returns. Tests change it to control the "LLM" answer.
        self.answer = GeminiAnswer(answer="A fake answer.", used_excerpts=[1])
        # What the rewrite step returns. Empty = "no rewrite", so the original question is used.
        self.rewritten = ""
        # Errors to raise, one per call, before behaving normally. Used by failure tests.
        self.embed_errors: list[Exception] = []
        self.generate_errors: list[Exception] = []
        # Records of every call, so tests can check what was sent (or that nothing was).
        self.embed_calls: list[list[str]] = []
        self.generate_calls: list[str] = []  # answer prompts
        self.rewrite_calls: list[str] = []  # rewrite prompts
        self.last_config = None  # settings of the last answer request (e.g. the system instruction)

    def _embed(self, text: str) -> list[float]:
        lowered = text.lower()
        for keyword, vector in self.topics.items():
            if keyword in lowered:
                return vector
        return self.other

    def embed_content(self, model, contents, config=None):
        self.embed_calls.append(list(contents))
        if self.embed_errors:
            raise self.embed_errors.pop(0)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=self._embed(text)) for text in contents]
        )

    def generate_content(self, model, contents, config=None):
        is_rewrite = config is None or config.response_schema is None
        if is_rewrite:
            self.rewrite_calls.append(contents)
        else:
            self.generate_calls.append(contents)
            self.last_config = config
        if self.generate_errors:
            raise self.generate_errors.pop(0)
        if is_rewrite:
            return SimpleNamespace(text=self.rewritten)
        return SimpleNamespace(parsed=self.answer)


class FakeGemini:
    """Stands in for `genai.Client`. Our code only uses `client.models`."""

    def __init__(self) -> None:
        self.models = FakeModels()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None: ignore backend/.env, so local tweaks can't change test results.
    return Settings(
        _env_file=None,
        google_api_key="test-key",
        chroma_path=tmp_path / "chroma_db",
        database_path=tmp_path / "data" / "conversations.db",
        max_upload_mb=1,  # keeps the "file too large" test small
    )


@pytest.fixture
def store(settings) -> VectorStore:
    # A new, empty database in a temporary folder for every test.
    return VectorStore(path=str(settings.chroma_path), collection_name="test")


@pytest.fixture
def conversation_store(settings) -> ConversationStore:
    # A new, empty SQLite file in the temporary folder for every test.
    return ConversationStore(settings.database_path)


@pytest.fixture
def fake_gemini() -> FakeGemini:
    return FakeGemini()


@pytest.fixture
def client(settings, store, conversation_store, fake_gemini):
    """An HTTP client for the app, with the real dependencies replaced by test ones."""
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_vector_store] = lambda: store
    app.dependency_overrides[get_conversation_store] = lambda: conversation_store
    app.dependency_overrides[get_gemini_client] = lambda: fake_gemini
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def no_sleep(monkeypatch) -> list[float]:
    """Replace time.sleep in the retry logic, so retries don't really wait. Returns the waits."""
    waits: list[float] = []
    monkeypatch.setattr("app.services.retrieval.time.sleep", waits.append)
    return waits


def build_pdf(pages: list[str]) -> bytes:
    """
    Build a PDF in memory: one string per page, one line of the PDF per text line.

    Real PDF files store Hebrew in "visual order" (left to right, as it appears on
    the page), and pypdf turns it back into reading order when extracting the text.
    So we store Hebrew lines reversed, exactly like a real PDF would.
    """
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for page_text in pages:
        pdf.setFont("Alef", 11)
        y = 800
        for line in page_text.split("\n"):
            pdf.drawString(40, y, line[::-1] if is_hebrew(line) else line)
            y -= 16
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@pytest.fixture
def make_pdf():
    return build_pdf


@pytest.fixture
def upload(client):
    """Send a file to POST /documents, like the browser would."""

    def send(data: bytes, filename: str = "handbook.pdf"):
        return client.post("/documents", files={"file": (filename, data, "application/pdf")})

    return send


@pytest.fixture
def new_conversation(client):
    """Create a conversation with the given documents selected; returns its id."""

    def create(document_ids: list[str]) -> int:
        response = client.post("/conversations", json={"document_ids": document_ids})
        assert response.status_code == 201
        return response.json()["id"]

    return create


@pytest.fixture
def ask_in(client):
    """Ask a question in an existing conversation."""

    def send(conversation_id: int, question: str):
        return client.post(
            "/chat", json={"conversation_id": conversation_id, "question": question}
        )

    return send
