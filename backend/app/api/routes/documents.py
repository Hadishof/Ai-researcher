"""Upload, list, view and delete documents."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from google import genai
from google.genai.errors import APIError

from app.core.config import Settings, get_settings
from app.core.gemini import get_gemini_client
from app.db.conversation_store import ConversationStore, get_conversation_store
from app.db.file_store import FileStore, get_file_store
from app.db.vector_store import VectorStore, get_vector_store
from app.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    DuplicateDocumentResponse,
)
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


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
    # Documents the 409 body in the API docs (/docs), since it is not the normal response.
    responses={status.HTTP_409_CONFLICT: {"model": DuplicateDocumentResponse}},
)
def upload_document(
    file: UploadFile = File(...),
    store: VectorStore = Depends(get_vector_store),
    files: FileStore = Depends(get_file_store),
    client: genai.Client = Depends(get_gemini_client),
    settings: Settings = Depends(get_settings),
) -> DocumentResponse | JSONResponse:
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
    except DuplicateDocumentError as error:
        # A document uploaded before PDFs were stored has no file yet: keep this copy.
        # (Same bytes -> same SHA-256 id, so it is exactly the same file.)
        if not files.exists(error.existing.document_id):
            files.save(error.existing.document_id, data)
        # Also return the document that is already in the library, so the frontend
        # can add it to the open chat instead of uploading it again.
        body = DuplicateDocumentResponse(
            detail="This document was already uploaded.",
            document_id=error.existing.document_id,
            filename=error.existing.filename,
        )
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())
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

    # Keep the original PDF so it can be viewed. The path comes from the SHA-256 id
    # only, never from the uploaded filename.
    files.save(info.document_id, data)

    return DocumentResponse(
        document_id=info.document_id,
        filename=info.filename,
        pages=info.pages,
        chunks=info.chunks,
        has_file=True,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    store: VectorStore = Depends(get_vector_store),
    conversations: ConversationStore = Depends(get_conversation_store),
    files: FileStore = Depends(get_file_store),
) -> DocumentListResponse:
    counts = conversations.conversation_counts()  # one query for all documents
    return DocumentListResponse(
        documents=[
            DocumentResponse(
                document_id=doc.document_id,
                filename=doc.filename,
                pages=doc.pages,
                chunks=doc.chunks,
                conversation_count=counts.get(doc.document_id, 0),
                has_file=files.exists(doc.document_id),
            )
            for doc in store.list_documents()
        ]
    )


@router.get(
    "/{document_id}/file",
    response_class=FileResponse,
    responses={
        status.HTTP_200_OK: {"content": {"application/pdf": {}}, "description": "The PDF file."},
        status.HTTP_404_NOT_FOUND: {"description": "No such document, or its file is not stored."},
    },
)
def get_document_file(
    document_id: str = DocumentId,
    store: VectorStore = Depends(get_vector_store),
    files: FileStore = Depends(get_file_store),
) -> FileResponse:
    """
    The original PDF, shown in the browser ("inline") rather than downloaded.
    Add #page=N to the URL to open it at a page (in browsers that support it).
    """
    found = store.find_documents([document_id])
    if not found or not files.exists(document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document file not found.")
    return FileResponse(
        files.path(document_id),
        media_type="application/pdf",
        # The original filename, as a label only (Starlette encodes it safely).
        filename=found[0].filename,
        content_disposition_type="inline",
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str = DocumentId,
    store: VectorStore = Depends(get_vector_store),
    conversations: ConversationStore = Depends(get_conversation_store),
    files: FileStore = Depends(get_file_store),
) -> None:
    """
    Delete the document's chunks and file, and remove it from every conversation's selection.
    Saved answers that cite it keep their text; their sources are shown as "deleted".
    """
    if not store.document_exists(document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    store.delete_document(document_id)
    files.delete(document_id)
    conversations.remove_document(document_id)
