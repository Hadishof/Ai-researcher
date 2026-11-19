"""Tests for storing, viewing and deleting the original PDF files."""

from urllib.parse import quote

import pytest

from app.db.file_store import FileStore

PAGES = ["Nimbus Robotics was founded in 2015.", "Support is open on weekdays."]


@pytest.fixture
def uploaded(upload, make_pdf):
    """Upload a small PDF; return (document_id, the exact bytes sent)."""
    data = make_pdf(PAGES)
    response = upload(data, "handbook.pdf")
    assert response.status_code == 201
    return response.json()["document_id"], data


def test_upload_saves_the_original_pdf(uploaded, file_store, settings):
    document_id, data = uploaded

    saved = settings.files_path / f"{document_id}.pdf"
    assert saved.read_bytes() == data
    assert file_store.exists(document_id)


def test_upload_and_list_report_that_the_file_is_stored(client, upload, make_pdf):
    response = upload(make_pdf(PAGES), "handbook.pdf")
    assert response.json()["has_file"] is True

    [document] = client.get("/documents").json()["documents"]
    assert document["has_file"] is True


def test_file_is_served_inline_as_pdf_with_its_filename(client, uploaded):
    document_id, data = uploaded

    response = client.get(f"/documents/{document_id}/file")

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="handbook.pdf"'


def test_hebrew_filename_is_encoded_in_the_header(client, upload, make_pdf):
    name = "מדיניות.pdf"
    document_id = upload(make_pdf(PAGES), name).json()["document_id"]

    response = client.get(f"/documents/{document_id}/file")

    assert response.headers["content-disposition"] == f"inline; filename*=utf-8''{quote(name)}"


def test_unknown_document_is_404(client):
    response = client.get(f"/documents/{'a' * 64}/file")
    assert response.status_code == 404


def test_document_without_a_stored_file_is_404(client, uploaded, file_store):
    document_id, _ = uploaded
    file_store.delete(document_id)  # like a document uploaded before files were stored

    assert client.get(f"/documents/{document_id}/file").status_code == 404
    [document] = client.get("/documents").json()["documents"]
    assert document["has_file"] is False


def test_malformed_id_is_422(client):
    for bad_id in ["123", "A" * 64, "g" * 64, "a" * 63 + ".pdf"]:
        assert client.get(f"/documents/{bad_id}/file").status_code == 422


def test_reuploading_an_old_document_stores_its_missing_file(uploaded, upload, file_store):
    document_id, data = uploaded
    file_store.delete(document_id)

    response = upload(data, "handbook.pdf")

    assert response.status_code == 409
    assert file_store.exists(document_id)


def test_deleting_a_document_deletes_its_file(client, uploaded, file_store):
    document_id, _ = uploaded

    assert client.delete(f"/documents/{document_id}").status_code == 204

    assert not file_store.exists(document_id)
    assert client.get(f"/documents/{document_id}/file").status_code == 404


# ---------- Path traversal: a path must never come from user input ----------


def test_uploaded_filename_is_never_used_as_a_path(uploaded, upload, make_pdf, settings, tmp_path):
    document_id = upload(make_pdf(["A different file."]), "../../evil.pdf").json()["document_id"]

    # Only <sha256>.pdf files inside the files folder; nothing written anywhere else.
    names = sorted(p.name for p in settings.files_path.iterdir())
    assert names == sorted([f"{uploaded[0]}.pdf", f"{document_id}.pdf"])
    assert not (tmp_path / "evil.pdf").exists()
    assert not list(tmp_path.parent.glob("evil.pdf"))


@pytest.mark.parametrize(
    "path",
    [
        "/documents/..%2F..%2Fsecret/file",
        "/documents/%2E%2E%2F%2E%2E%2Fconversations.db/file",
        "/documents/..\\..\\secret/file",
    ],
)
def test_traversal_in_the_url_is_rejected(client, path):
    assert client.get(path).status_code in (404, 422)


@pytest.mark.parametrize("bad_id", ["../secret", "..\\secret", "a" * 64 + "/../x", ""])
def test_file_store_refuses_ids_that_are_not_a_sha256(tmp_path, bad_id):
    store = FileStore(tmp_path)
    with pytest.raises(ValueError):
        store.path(bad_id)
