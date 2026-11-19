"""Shapes of the data sent to and returned by the /conversations endpoints."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.chat import Source

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
# A document id is a SHA-256 hash: exactly 64 lowercase hex characters.
DocumentId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


# --- Requests ------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    document_ids: list[DocumentId] = Field(default_factory=list)


class RenameConversationRequest(BaseModel):
    title: Title


class SetDocumentsRequest(BaseModel):
    document_ids: list[DocumentId]


# --- Responses -----------------------------------------------------------------


class ConversationDocument(BaseModel):
    """A document selected for a conversation."""

    document_id: str
    filename: str


class ConversationDocumentsResponse(BaseModel):
    documents: list[ConversationDocument]


class SavedSource(Source):
    """A source of a saved answer. The document may have been deleted since then."""

    document_deleted: bool


class MessageResponse(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    found: bool | None  # None for the user's questions
    sources: list[SavedSource]
    created_at: datetime


class ConversationSummary(BaseModel):
    """One row of the conversation list."""

    id: int
    title: str | None  # None until the first question (the frontend shows "New chat")
    updated_at: datetime


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class ConversationResponse(BaseModel):
    """One conversation with its selected documents and all its messages."""

    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime
    documents: list[ConversationDocument]
    messages: list[MessageResponse]
