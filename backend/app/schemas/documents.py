"""Shapes of the data returned by the /documents endpoints."""

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    document_id: str  # SHA-256 hash of the file's contents
    filename: str
    pages: int
    chunks: int
    # How many conversations have this document selected.
    # A newly uploaded document is not in any conversation yet, so it starts at 0.
    conversation_count: int = 0


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class DuplicateDocumentResponse(BaseModel):
    """The 409 body: the error message plus the document that is already in the library."""

    detail: str
    document_id: str
    filename: str
