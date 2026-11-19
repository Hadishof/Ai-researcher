"""Turns an uploaded PDF into embedded chunks and saves them in the vector store."""

import hashlib
import re
import unicodedata
from io import BytesIO

from google import genai
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import Settings
from app.db.vector_store import DocumentInfo, StoredChunk, VectorStore
from app.services.retrieval import embed_texts


class InvalidPdfError(Exception):
    """The file is not a PDF we can open."""


class NoTextError(Exception):
    """The PDF opened, but has no extractable text (for example, a scanned image)."""


class DuplicateDocumentError(Exception):
    """This exact file was already uploaded. `existing` is the document already stored."""

    def __init__(self, existing: DocumentInfo):
        super().__init__("This document was already uploaded.")
        self.existing = existing


# Paragraphs are separated by one or more blank lines.
PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# A single line break: in a PDF, the end of a line of text (a heading, a table row,
# a list item, or just where a long sentence wrapped).
LINE_BREAK = re.compile(r"\n")
# A sentence ends with . ! ? … or the Hebrew sof pasuq (׃), followed by whitespace.
# This works for Hebrew too: Hebrew uses the same punctuation marks.
SENTENCE_END = re.compile(r"(?<=[.!?…׃])\s+")
WHITESPACE = re.compile(r"\s+")


def compute_document_id(data: bytes) -> str:
    """SHA-256 fingerprint of the file's bytes. Same file -> same id, always."""
    return hashlib.sha256(data).hexdigest()


def looks_like_pdf(data: bytes) -> bool:
    """Every PDF file starts with the bytes '%PDF-' (checked on content, not on the filename)."""
    return b"%PDF-" in data[:1024]


def clean_filename(name: str | None) -> str:
    """Keep only the last part of the name. It is used as a label, never as a path."""
    if not name:
        return "document.pdf"
    return name.replace("\\", "/").rsplit("/", 1)[-1][:200] or "document.pdf"


def read_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    """
    Return (page_number, text) for every page, numbered from 1.

    The text is NFKC-normalized: PDFs often store letter pairs as one special
    character (a "ligature", e.g. "ﬁ" in "ﬁlter"). To the embedding model and to
    a text search, "ﬁlter" and "filter" are different words. NFKC replaces such
    characters with their plain letters, so "ﬁlter" becomes "filter".
    """
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise InvalidPdfError("This PDF is password-protected.")
        return [
            (number, unicodedata.normalize("NFKC", page.extract_text() or ""))
            for number, page in enumerate(reader.pages, 1)
        ]
    except PdfReadError:
        raise InvalidPdfError("This PDF is damaged or cannot be read.") from None


def _hard_split(text: str, chunk_size: int) -> list[str]:
    """Last resort for text with no sentence breaks: cut at a space, or mid-word if there is none."""
    parts = []
    while len(text) > chunk_size:
        cut = text.rfind(" ", 0, chunk_size + 1)
        if cut <= chunk_size // 2:  # no space in a sensible place: cut exactly at the limit
            cut = chunk_size
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def _overlap_tail(text: str, overlap: int) -> str:
    """The last `overlap` characters of a chunk, starting at a whole word."""
    if overlap == 0 or len(text) <= overlap:
        return ""
    tail = text[-overlap:]
    # The first space or line break: the chunk's pieces are joined with line breaks.
    first_break = WHITESPACE.search(tail)
    return tail[first_break.end() :] if first_break else tail


def _split_line(line: str, chunk_size: int) -> list[str]:
    """A line too long for one chunk: split it at sentence ends, and cut a sentence only as a last resort."""
    pieces = []
    for sentence in SENTENCE_END.split(line):
        if len(sentence) <= chunk_size:
            pieces.append(sentence)
        else:
            pieces.extend(_hard_split(sentence, chunk_size))
    return pieces


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Split text into chunks of at most `chunk_size` characters.

    Order of preference: keep whole paragraphs, then whole lines, then whole
    sentences, and only cut mid-text when a single sentence is longer than
    `chunk_size`. Lines matter because PDF text often has no blank lines at all:
    a heading or a table row ("Weight 38 kg") has no full stop, so splitting
    such a page by sentences would glue rows together or cut them apart.
    Each new chunk starts with the end of the previous one (`overlap`), so an
    idea that falls on a boundary is not lost.
    """
    # 1. Break the text into pieces that each fit in one chunk.
    pieces = []
    for paragraph in PARAGRAPH_BREAK.split(text):
        joined = WHITESPACE.sub(" ", paragraph).strip()  # join the PDF's line breaks
        if not joined:
            continue
        if len(joined) <= chunk_size:
            pieces.append(joined)
            continue
        # Too long for one chunk: keep each line whole instead.
        for line in LINE_BREAK.split(paragraph):
            line = WHITESPACE.sub(" ", line).strip()
            if not line:
                continue
            if len(line) <= chunk_size:
                pieces.append(line)
            else:
                pieces.extend(_split_line(line, chunk_size))

    # 2. Pack pieces into chunks, adding overlap when a new chunk starts.
    chunks = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n{piece}" if current else piece
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        chunks.append(current)
        tail = _overlap_tail(current, overlap)
        current = f"{tail} {piece}" if tail and len(tail) + 1 + len(piece) <= chunk_size else piece
    if current:
        chunks.append(current)
    return chunks


def ingest_pdf(
    data: bytes,
    filename: str,
    store: VectorStore,
    client: genai.Client,
    settings: Settings,
) -> DocumentInfo:
    """Fingerprint -> duplicate check -> read pages -> chunk -> embed -> save."""
    document_id = compute_document_id(data)
    existing = store.find_documents([document_id])
    if existing:
        raise DuplicateDocumentError(existing[0])

    pages = read_pdf_pages(data)

    # Chunk each page separately, so every chunk knows its exact page number.
    page_chunks: list[tuple[int, str]] = []
    for page_number, page_text in pages:
        for chunk in split_text(page_text, settings.chunk_size, settings.chunk_overlap):
            page_chunks.append((page_number, chunk))
    if not page_chunks:
        raise NoTextError()

    embeddings = embed_texts(
        client,
        [text for _, text in page_chunks],
        model=settings.embedding_model,
        task_type="RETRIEVAL_DOCUMENT",
    )

    store.add_chunks(
        [
            StoredChunk(
                id=f"{document_id}-{index}",
                text=text,
                embedding=embedding,
                document_id=document_id,
                filename=filename,
                page=page_number,
                page_count=len(pages),
            )
            for index, ((page_number, text), embedding) in enumerate(zip(page_chunks, embeddings))
        ]
    )
    return DocumentInfo(
        document_id=document_id,
        filename=filename,
        pages=len(pages),
        chunks=len(page_chunks),
    )
