"""The only file that talks to SQLite: saved conversations, their messages and their documents."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

# "IF NOT EXISTS": safe to run every time the app starts; existing data is kept.
SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT,                -- NULL until the first question gives it one
    created_at  TEXT NOT NULL,       -- ISO 8601 time in UTC
    updated_at  TEXT NOT NULL        -- changes every time a message is added
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER NOT NULL
                     REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content          TEXT NOT NULL,
    found            INTEGER,         -- 1 or 0 for answers, NULL for questions
    sources          TEXT NOT NULL DEFAULT '[]',   -- JSON list of sources
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, id);

-- Which documents each conversation searches (many-to-many).
-- document_id has no foreign key: documents live in ChromaDB, not in this database,
-- so the documents route removes these rows itself when a document is deleted.
CREATE TABLE IF NOT EXISTS conversation_documents (
    conversation_id  INTEGER NOT NULL
                     REFERENCES conversations(id) ON DELETE CASCADE,
    document_id      TEXT NOT NULL,
    PRIMARY KEY (conversation_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_documents_document
    ON conversation_documents(document_id);
"""


@dataclass
class Conversation:
    id: int
    title: str | None
    created_at: str
    updated_at: str


@dataclass
class Message:
    id: int
    conversation_id: int
    role: str  # "user" or "assistant"
    content: str
    found: bool | None  # None for the user's questions
    sources: list[dict]
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_message(row: sqlite3.Row) -> Message:
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        found=None if row["found"] is None else bool(row["found"]),
        sources=json.loads(row["sources"]),
        created_at=row["created_at"],
    )


class ConversationStore:
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """
        Open a short connection for one operation, then close it.

        - foreign_keys = ON: SQLite ignores foreign keys (and ON DELETE CASCADE)
          unless every connection turns them on.
        - `with connection`: commits if the block succeeds, rolls back if it fails,
          so a group of statements is saved all together or not at all.
        A new connection per operation is safe with FastAPI, which runs requests on
        several threads; one SQLite connection should not be shared between threads.
        """
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row  # read columns by name: row["title"]
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    # --- Conversations ---------------------------------------------------------

    def create_conversation(self, document_ids: list[str]) -> Conversation:
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO conversations (title, created_at, updated_at) VALUES (NULL, ?, ?)",
                (now, now),
            )
            conversation_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO conversation_documents (conversation_id, document_id) VALUES (?, ?)",
                [(conversation_id, document_id) for document_id in document_ids],
            )
        return Conversation(id=conversation_id, title=None, created_at=now, updated_at=now)

    def list_conversations(self) -> list[Conversation]:
        """Newest activity first. The id breaks ties between equal times."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [_to_conversation(row) for row in rows]

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return _to_conversation(row) if row else None

    def rename_conversation(self, conversation_id: int, title: str) -> Conversation | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id)
            )
        return self.get_conversation(conversation_id)

    def delete_conversation(self, conversation_id: int) -> bool:
        """Its messages and document selections are deleted by ON DELETE CASCADE."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
        return cursor.rowcount > 0

    def delete_all_conversations(self) -> int:
        """Delete every conversation; returns how many. Documents (in ChromaDB) are not touched."""
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM conversations")
        return cursor.rowcount

    # --- Messages --------------------------------------------------------------

    def add_exchange(
        self,
        conversation_id: int,
        question: str,
        answer: str,
        found: bool,
        sources: list[dict],
        title: str,
    ) -> None:
        """
        Save a question and its answer in one transaction, and mark the conversation
        as updated. `title` is used only if the conversation has no title yet, so a
        name chosen by the user is never replaced.
        """
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO messages (conversation_id, role, content, found, sources, created_at) "
                "VALUES (?, 'user', ?, NULL, '[]', ?)",
                (conversation_id, question, now),
            )
            connection.execute(
                "INSERT INTO messages (conversation_id, role, content, found, sources, created_at) "
                "VALUES (?, 'assistant', ?, ?, ?, ?)",
                (conversation_id, answer, int(found), json.dumps(sources, ensure_ascii=False), now),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ?, title = COALESCE(title, ?) WHERE id = ?",
                (now, title, conversation_id),
            )

    def get_messages(self, conversation_id: int) -> list[Message]:
        """All messages of a conversation, oldest first."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return [_to_message(row) for row in rows]

    def recent_messages(self, conversation_id: int, limit: int) -> list[Message]:
        """The last `limit` messages, oldest first (the order they were written in)."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [_to_message(row) for row in reversed(rows)]

    # --- Documents selected for each conversation ------------------------------

    def get_document_ids(self, conversation_id: int) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT document_id FROM conversation_documents WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
        return [row["document_id"] for row in rows]

    def set_document_ids(self, conversation_id: int, document_ids: list[str]) -> None:
        """Replace the whole selection: delete the old rows, insert the new ones, in one transaction."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM conversation_documents WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.executemany(
                "INSERT INTO conversation_documents (conversation_id, document_id) VALUES (?, ?)",
                [(conversation_id, document_id) for document_id in document_ids],
            )

    def remove_document(self, document_id: str) -> int:
        """Remove a deleted document from every conversation; returns how many it was in."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversation_documents WHERE document_id = ?", (document_id,)
            )
        return cursor.rowcount

    def conversation_counts(self) -> dict[str, int]:
        """For each document: how many conversations have it selected."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT document_id, COUNT(*) AS conversations "
                "FROM conversation_documents GROUP BY document_id"
            ).fetchall()
        return {row["document_id"]: row["conversations"] for row in rows}


@lru_cache
def get_conversation_store() -> ConversationStore:
    return ConversationStore(get_settings().database_path)
