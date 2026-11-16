"""Tests for POST /documents, GET /documents and DELETE /documents/{id}."""

import hashlib
from io import BytesIO

from google.genai.errors import ClientError, ServerError
from reportlab.pdfgen import canvas

HANDBOOK = [
    "Nimbus Robotics was founded by Dana Levi.",
    "Support responds to critical problems within 4 hours.",
    "העובדים מקבלים עשרים ימי חופשה בשנה",  # Hebrew page
    "The maximum load of the robot arm is 50 kg.",
]


def rate_limit_error(seconds: float = 7.5) -> ClientError:
    """The error Gemini returns when the free-tier limit is reached."""
    message = f"Quota exceeded. Please retry in {seconds}s."
    return ClientError(429, {"error": {"code": 429, "message": message}})


def server_error() -> ServerError:
    return ServerError(500, {"error": {"code": 500, "message": "Internal error"}})


# --- Upload: success ------------------------------------------------------------


def test_upload_pdf(upload, make_pdf, fake_gemini):
    data = make_pdf(HANDBOOK)

    response = upload(data, "handbook.pdf")

    assert response.status_code == 201
    assert response.json() == {
        "document_id": hashlib.sha256(data).hexdigest(),  # the id is the file's fingerprint
        "filename": "handbook.pdf",
        "pages": 4,
        "chunks": 4,  # each short page fits in one chunk
    }
    # All chunks were embedded in one request, including the Hebrew page's text.
    assert len(fake_gemini.models.embed_calls) == 1
    assert "העובדים מקבלים עשרים ימי חופשה בשנה" in fake_gemini.models.embed_calls[0]


def test_uploaded_filename_is_never_used_as_a_path(upload, make_pdf):
    response = upload(make_pdf(["Some text."]), "../../secret/handbook.pdf")

    assert response.status_code == 201
    assert response.json()["filename"] == "handbook.pdf"


# --- Upload: rejected files ----------------------------------------------------


def test_upload_same_file_twice_is_rejected(upload, make_pdf, fake_gemini):
    data = make_pdf(HANDBOOK)
    upload(data)

    response = upload(data, "another-name.pdf")  # same bytes, different name

    assert response.status_code == 409
    # The duplicate was caught before embedding anything again.
    assert len(fake_gemini.models.embed_calls) == 1


def test_upload_non_pdf_is_rejected(upload):
    response = upload(b"Just some plain text, not a PDF.", "notes.pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported."


def test_upload_empty_file_is_rejected(upload):
    response = upload(b"", "empty.pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "The file is empty."


def test_upload_too_large_is_rejected(upload, settings):
    too_big = b"%PDF-" + b"0" * (settings.max_upload_mb * 1024 * 1024)

    response = upload(too_big, "big.pdf")

    assert response.status_code == 413


def test_upload_pdf_without_text_is_rejected(upload, make_pdf, fake_gemini):
    response = upload(make_pdf([""]), "scan.pdf")  # a page with no text, like a scanned image

    assert response.status_code == 422
    assert fake_gemini.models.embed_calls == []


def test_upload_damaged_pdf_is_rejected(upload, fake_gemini):
    # Starts like a PDF (so it passes the first check), but the rest is not a real PDF.
    response = upload(b"%PDF-1.7\nthis is not really a pdf", "broken.pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "This PDF is damaged or cannot be read."
    assert fake_gemini.models.embed_calls == []


def test_upload_password_protected_pdf_is_rejected(upload, fake_gemini):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, encrypt="secret")  # reportlab encrypts it with this password
    pdf.drawString(40, 800, "Confidential text.")
    pdf.showPage()
    pdf.save()

    response = upload(buffer.getvalue(), "locked.pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "This PDF is password-protected."
    assert fake_gemini.models.embed_calls == []


# --- Upload: Gemini failures ---------------------------------------------------


def test_upload_retries_after_rate_limit_then_succeeds(upload, make_pdf, fake_gemini, no_sleep):
    fake_gemini.models.embed_errors = [rate_limit_error(7.5), rate_limit_error(2)]

    response = upload(make_pdf(HANDBOOK))

    assert response.status_code == 201
    assert len(fake_gemini.models.embed_calls) == 3  # 2 failures + 1 success
    # It waited the time Gemini asked for, plus one second, before each retry.
    assert no_sleep == [8.5, 3.0]


def test_upload_returns_429_when_rate_limit_continues(upload, make_pdf, fake_gemini, no_sleep):
    fake_gemini.models.embed_errors = [rate_limit_error() for _ in range(10)]

    response = upload(make_pdf(HANDBOOK))

    assert response.status_code == 429
    assert len(fake_gemini.models.embed_calls) == 4  # first try + 3 retries, then give up
    assert len(no_sleep) == 3


def test_upload_returns_502_when_gemini_fails(upload, make_pdf, fake_gemini, no_sleep):
    fake_gemini.models.embed_errors = [server_error()]

    response = upload(make_pdf(HANDBOOK))

    assert response.status_code == 502
    assert len(fake_gemini.models.embed_calls) == 1  # other errors are not retried
    assert no_sleep == []


def test_failed_upload_saves_nothing(client, upload, make_pdf, fake_gemini, no_sleep):
    fake_gemini.models.embed_errors = [server_error()]
    upload(make_pdf(HANDBOOK))

    assert client.get("/documents").json() == {"documents": []}


# --- List and delete -----------------------------------------------------------


def test_list_is_empty_at_start(client):
    response = client.get("/documents")

    assert response.status_code == 200
    assert response.json() == {"documents": []}


def test_list_shows_uploaded_documents(client, upload, make_pdf):
    first = upload(make_pdf(HANDBOOK), "handbook.pdf").json()
    second = upload(make_pdf(["Another document."]), "another.pdf").json()

    response = client.get("/documents")

    assert response.status_code == 200
    assert response.json() == {"documents": [second, first]}  # sorted by filename


def test_delete_document(client, upload, make_pdf):
    document_id = upload(make_pdf(HANDBOOK)).json()["document_id"]

    first_delete = client.delete(f"/documents/{document_id}")
    second_delete = client.delete(f"/documents/{document_id}")

    assert first_delete.status_code == 204
    assert second_delete.status_code == 404
    assert client.get("/documents").json() == {"documents": []}


def test_delete_with_invalid_id_is_rejected(client):
    response = client.delete("/documents/not-a-real-id")

    assert response.status_code == 422  # the id must be 64 hex characters
