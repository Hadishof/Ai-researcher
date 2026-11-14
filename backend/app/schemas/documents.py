"""Shapes of the data returned by the /documents endpoints."""

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    document_id: str  # SHA-256 hash of the file's contents
    filename: str
    pages: int
    chunks: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
