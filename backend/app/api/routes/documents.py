"""Upload, list and delete documents."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from google import genai
from google.genai.errors import APIError

from app.core.config import Settings, get_settings
from app.core.gemini import get_gemini_client
from app.db.vector_store import VectorStore, get_vector_store
from app.schemas.documents import DocumentListResponse, DocumentResponse
from app.services.ingestion import (
    DuplicateDocumentError,
    InvalidPdfError,
    NoTextError,
    clean_filename,
    ingest_pdf,
    looks_like_pdf,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# A document id is a SHA-256 hash: exactly 64 lowercase hex characters.
DocumentId = Path(pattern=r"^[0-9a-f]{64}$", description="The document's SHA-256 hash")


# Routes are plain `def` (not `async def`) because they make slow, blocking calls
# (Gemini, ChromaDB). FastAPI runs plain `def` routes in a thread pool, so one slow
# request does not freeze the whole server.


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DocumentResponse)
def upload_document(
    file: UploadFile = File(...),
    store: VectorStore = Depends(get_vector_store),
    client: genai.Client = Depends(get_gemini_client),
    settings: Settings = Depends(get_settings),
) -> DocumentResponse:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)  # read one extra byte to detect "too big"

    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty.")
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The file is larger than {settings.max_upload_mb} MB.",
        )
    if not looks_like_pdf(data):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files are supported.")

    try:
        info = ingest_pdf(data, clean_filename(file.filename), store, client, settings)
    except DuplicateDocumentError:
        raise HTTPException(status.HTTP_409_CONFLICT, "This document was already uploaded.")
    except InvalidPdfError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))
    except NoTextError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "No readable text was found in this PDF (it may be a scanned image).",
        )
    except APIError as error:
        if error.code == 429:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "The AI service's rate limit was reached. Please try again in a minute.",
            )
        logger.exception("Gemini embedding request failed")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The embedding service failed. Please try again."
        )

    return DocumentResponse(
        document_id=info.document_id,
        filename=info.filename,
        pages=info.pages,
        chunks=info.chunks,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(store: VectorStore = Depends(get_vector_store)) -> DocumentListResponse:
    return DocumentListResponse(
        documents=[
            DocumentResponse(
                document_id=doc.document_id,
                filename=doc.filename,
                pages=doc.pages,
                chunks=doc.chunks,
            )
            for doc in store.list_documents()
        ]
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str = DocumentId,
    store: VectorStore = Depends(get_vector_store),
) -> None:
    if not store.document_exists(document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    store.delete_document(document_id)
