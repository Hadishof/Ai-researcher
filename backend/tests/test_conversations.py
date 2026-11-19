"""Tests for the /conversations endpoints: create, list, open, rename, delete, choose documents."""

import sqlite3

import pytest

HANDBOOK = [
    "Nimbus Robotics was founded by Dana Levi.",
    "Support responds to critical problems within 4 hours.",
]
UNKNOWN_DOCUMENT = "0" * 64  # a valid-looking id that matches no document


@pytest.fixture
def handbook_id(upload, make_pdf) -> str:
    return upload(make_pdf(HANDBOOK), "handbook.pdf").json()["document_id"]


@pytest.fixture
def other_id(upload, make_pdf) -> str:
    return upload(make_pdf(["Another document."]), "other.pdf").json()["document_id"]


def count_rows(settings, table: str) -> int:
    """Look straight into the SQLite file, to check what is really stored."""
    connection = sqlite3.connect(settings.database_path)
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        connection.close()


# --- Create --------------------------------------------------------------------


def test_create_empty_conversation(client):
    response = client.post("/conversations")  # no body at all

    assert response.status_code == 201
    body = response.json()
    assert body["title"] is None  # set later, from the first question
    assert body["documents"] == []
    assert body["messages"] == []
    assert body["created_at"] == body["updated_at"]


def test_create_conversation_with_documents(client, handbook_id, other_id):
    response = client.post("/conversations", json={"document_ids": [other_id, handbook_id]})

    assert response.status_code == 201
    assert response.json()["documents"] == [  # sorted by filename
        {"document_id": handbook_id, "filename": "handbook.pdf"},
        {"document_id": other_id, "filename": "other.pdf"},
    ]


def test_create_with_unknown_document_returns_404(client, handbook_id, settings):
    response = client.post(
        "/conversations", json={"document_ids": [handbook_id, UNKNOWN_DOCUMENT]}
    )

    assert response.status_code == 404
    assert count_rows(settings, "conversations") == 0  # nothing was created


def test_create_with_invalid_document_id_returns_422(client):
    response = client.post("/conversations", json={"document_ids": ["not-a-hash"]})

    assert response.status_code == 422


# --- List and open -------------------------------------------------------------


def test_list_is_empty_at_start(client):
    assert client.get("/conversations").json() == {"conversations": []}


def test_list_shows_newest_activity_first(client, handbook_id, new_conversation, ask_in):
    first = new_conversation([handbook_id])
    second = new_conversation([handbook_id])

    ids = [c["id"] for c in client.get("/conversations").json()["conversations"]]
    assert ids == [second, first]  # the newest conversation first

    ask_in(first, "Who founded Nimbus Robotics?")  # new activity moves it to the top

    listed = client.get("/conversations").json()["conversations"]
    assert [c["id"] for c in listed] == [first, second]
    assert listed[0]["title"] == "Who founded Nimbus Robotics?"
    assert set(listed[0]) == {"id", "title", "updated_at"}


def test_get_conversation_with_messages(client, handbook_id, new_conversation, ask_in):
    conversation_id = new_conversation([handbook_id])
    ask_in(conversation_id, "Who founded Nimbus Robotics?")
    ask_in(conversation_id, "How fast does support respond?")

    response = client.get(f"/conversations/{conversation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == [{"document_id": handbook_id, "filename": "handbook.pdf"}]
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "Who founded Nimbus Robotics?"),
        ("assistant", "A fake answer."),
        ("user", "How fast does support respond?"),
        ("assistant", "A fake answer."),
    ]


def test_get_unknown_conversation_returns_404(client):
    response = client.get("/conversations/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found."


# --- Rename --------------------------------------------------------------------


def test_rename_conversation(client, new_conversation):
    conversation_id = new_conversation([])

    response = client.patch(f"/conversations/{conversation_id}", json={"title": "  HR rules  "})

    assert response.status_code == 200
    assert response.json()["title"] == "HR rules"  # spaces around it are removed
    assert client.get(f"/conversations/{conversation_id}").json()["title"] == "HR rules"


@pytest.mark.parametrize("title", ["", "   ", "x" * 101])
def test_rename_with_invalid_title_returns_422(client, new_conversation, title):
    conversation_id = new_conversation([])

    response = client.patch(f"/conversations/{conversation_id}", json={"title": title})

    assert response.status_code == 422


def test_rename_unknown_conversation_returns_404(client):
    response = client.patch("/conversations/999", json={"title": "New name"})

    assert response.status_code == 404


# --- Choose documents ----------------------------------------------------------


def test_put_documents_replaces_the_selection(client, handbook_id, other_id, new_conversation):
    conversation_id = new_conversation([handbook_id])

    response = client.put(
        f"/conversations/{conversation_id}/documents", json={"document_ids": [other_id]}
    )

    expected = [{"document_id": other_id, "filename": "other.pdf"}]
    assert response.status_code == 200
    assert response.json() == {"documents": expected}
    assert client.get(f"/conversations/{conversation_id}").json()["documents"] == expected


def test_put_documents_with_empty_list_clears_the_selection(client, handbook_id, new_conversation):
    conversation_id = new_conversation([handbook_id])

    client.put(f"/conversations/{conversation_id}/documents", json={"document_ids": []})

    assert client.get(f"/conversations/{conversation_id}").json()["documents"] == []


def test_put_documents_ignores_repeated_ids(client, handbook_id, new_conversation):
    conversation_id = new_conversation([])

    response = client.put(
        f"/conversations/{conversation_id}/documents",
        json={"document_ids": [handbook_id, handbook_id]},
    )

    assert response.status_code == 200
    assert len(response.json()["documents"]) == 1


def test_put_unknown_document_returns_404_and_keeps_the_selection(
    client, handbook_id, new_conversation
):
    conversation_id = new_conversation([handbook_id])

    response = client.put(
        f"/conversations/{conversation_id}/documents",
        json={"document_ids": [UNKNOWN_DOCUMENT]},
    )

    assert response.status_code == 404
    documents = client.get(f"/conversations/{conversation_id}").json()["documents"]
    assert [d["document_id"] for d in documents] == [handbook_id]


def test_put_documents_of_unknown_conversation_returns_404(client, handbook_id):
    response = client.put("/conversations/999/documents", json={"document_ids": [handbook_id]})

    assert response.status_code == 404


# --- Delete --------------------------------------------------------------------


def test_delete_conversation_also_deletes_its_messages(
    client, handbook_id, new_conversation, ask_in, settings
):
    deleted = new_conversation([handbook_id])
    kept = new_conversation([handbook_id])
    ask_in(deleted, "Who founded Nimbus Robotics?")
    ask_in(kept, "Who founded Nimbus Robotics?")

    first_delete = client.delete(f"/conversations/{deleted}")
    second_delete = client.delete(f"/conversations/{deleted}")

    assert first_delete.status_code == 204
    assert second_delete.status_code == 404
    assert client.get(f"/conversations/{deleted}").status_code == 404
    # ON DELETE CASCADE removed its 2 messages and its document selection;
    # the other conversation's rows are still there.
    assert count_rows(settings, "messages") == 2
    assert count_rows(settings, "conversation_documents") == 1
    # The document itself is untouched.
    assert [d["document_id"] for d in client.get("/documents").json()["documents"]] == [
        handbook_id
    ]


def test_delete_all_conversations_keeps_documents(
    client, handbook_id, other_id, new_conversation, ask_in, settings
):
    documents_before = client.get("/documents").json()
    for _ in range(3):
        conversation_id = new_conversation([handbook_id, other_id])
        ask_in(conversation_id, "Who founded Nimbus Robotics?")

    response = client.delete("/conversations")

    assert response.status_code == 204
    assert client.get("/conversations").json() == {"conversations": []}
    assert count_rows(settings, "conversations") == 0
    assert count_rows(settings, "messages") == 0
    assert count_rows(settings, "conversation_documents") == 0
    # Same documents, same chunks; no conversation uses them any more.
    assert client.get("/documents").json() == documents_before


def test_delete_all_when_there_are_none(client):
    assert client.delete("/conversations").status_code == 204
