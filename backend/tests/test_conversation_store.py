"""Tests for the SQLite repository on its own (no HTTP), using a temporary database file."""

import sqlite3

import pytest

from app.db.conversation_store import ConversationStore

DOC_A = "a" * 64
DOC_B = "b" * 64


@pytest.fixture
def db(tmp_path) -> ConversationStore:
    return ConversationStore(tmp_path / "data" / "test.db")


def save_exchange(db: ConversationStore, conversation_id: int, question: str = "Question?"):
    db.add_exchange(
        conversation_id,
        question=question,
        answer="Answer.",
        found=True,
        sources=[{"document_id": DOC_A, "filename": "a.pdf", "page": 1, "score": 0.9}],
        title=question,
    )


def test_creates_the_folder_and_tables(tmp_path):
    path = tmp_path / "new-folder" / "conversations.db"

    ConversationStore(path)

    assert path.exists()
    connection = sqlite3.connect(path)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    connection.close()
    assert {"conversations", "messages", "conversation_documents"} <= tables


def test_data_survives_reopening_the_database(tmp_path):
    path = tmp_path / "conversations.db"
    conversation = ConversationStore(path).create_conversation([DOC_A])

    reopened = ConversationStore(path)  # like restarting the server

    assert reopened.get_conversation(conversation.id) == conversation
    assert reopened.get_document_ids(conversation.id) == [DOC_A]


def test_create_and_get(db):
    created = db.create_conversation([])

    assert created.title is None
    assert db.get_conversation(created.id) == created
    assert db.get_conversation(999) is None


def test_list_newest_activity_first(db):
    first = db.create_conversation([])
    second = db.create_conversation([])
    assert [c.id for c in db.list_conversations()] == [second.id, first.id]

    save_exchange(db, first.id)

    assert [c.id for c in db.list_conversations()] == [first.id, second.id]


def test_add_exchange_saves_both_messages(db):
    conversation = db.create_conversation([])

    db.add_exchange(
        conversation.id,
        question="כמה ימי חופשה?",  # Hebrew is stored and read back unchanged
        answer="עשרים ימים.",
        found=True,
        sources=[{"document_id": DOC_A, "filename": "חוברת.pdf", "page": 3, "score": 0.81}],
        title="כמה ימי חופשה?",
    )

    question, answer = db.get_messages(conversation.id)
    assert (question.role, question.content, question.found, question.sources) == (
        "user",
        "כמה ימי חופשה?",
        None,
        [],
    )
    assert (answer.role, answer.content, answer.found) == ("assistant", "עשרים ימים.", True)
    assert answer.sources == [
        {"document_id": DOC_A, "filename": "חוברת.pdf", "page": 3, "score": 0.81}
    ]
    assert db.get_conversation(conversation.id).title == "כמה ימי חופשה?"


def test_title_is_set_only_once(db):
    conversation = db.create_conversation([])

    save_exchange(db, conversation.id, "First question?")
    save_exchange(db, conversation.id, "Second question?")

    assert db.get_conversation(conversation.id).title == "First question?"


def test_rename(db):
    conversation = db.create_conversation([])

    renamed = db.rename_conversation(conversation.id, "My chat")

    assert renamed.title == "My chat"
    assert db.rename_conversation(999, "Nothing") is None


def test_recent_messages_returns_the_last_ones_oldest_first(db):
    conversation = db.create_conversation([])
    save_exchange(db, conversation.id, "Q1?")
    save_exchange(db, conversation.id, "Q2?")

    recent = db.recent_messages(conversation.id, limit=3)

    assert [m.content for m in recent] == ["Answer.", "Q2?", "Answer."]


def test_messages_need_an_existing_conversation(db):
    # The foreign key is enforced: a message can't point to a conversation that doesn't exist.
    with pytest.raises(sqlite3.IntegrityError):
        save_exchange(db, 999)


def test_delete_cascades_to_messages_and_document_selection(db):
    deleted = db.create_conversation([DOC_A])
    kept = db.create_conversation([DOC_A])
    save_exchange(db, deleted.id)
    save_exchange(db, kept.id)

    assert db.delete_conversation(deleted.id) is True
    assert db.delete_conversation(deleted.id) is False  # already gone

    assert db.get_messages(deleted.id) == []
    assert db.get_document_ids(deleted.id) == []
    assert len(db.get_messages(kept.id)) == 2  # other conversations are not touched
    assert db.conversation_counts() == {DOC_A: 1}


def test_delete_all(db):
    for _ in range(3):
        conversation = db.create_conversation([DOC_A])
        save_exchange(db, conversation.id)

    assert db.delete_all_conversations() == 3
    assert db.list_conversations() == []
    assert db.conversation_counts() == {}


def test_set_document_ids_replaces_the_selection(db):
    conversation = db.create_conversation([DOC_A])

    db.set_document_ids(conversation.id, [DOC_B])

    assert db.get_document_ids(conversation.id) == [DOC_B]


def test_remove_document_and_conversation_counts(db):
    db.create_conversation([DOC_A, DOC_B])
    db.create_conversation([DOC_A])
    assert db.conversation_counts() == {DOC_A: 2, DOC_B: 1}

    assert db.remove_document(DOC_A) == 2

    assert db.conversation_counts() == {DOC_B: 1}
