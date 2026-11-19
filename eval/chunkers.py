"""
The chunking setups compared in the experiments: our chunker and LangChain's, at several sizes.

Both chunkers split each PDF page separately (like the app), so every chunk
knows its page number, and both measure size and overlap in characters.
"""

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.ingestion import compute_document_id, read_pdf_pages, split_text
from dataset import DATA_DIR

# The app's default is 150 overlap for 1000 characters. Every size keeps this ratio.
OVERLAP_RATIO = 0.15


@dataclass(frozen=True)
class Setup:
    chunker: str  # "ours" or "langchain"
    chunk_size: int

    @property
    def overlap(self) -> int:
        return round(self.chunk_size * OVERLAP_RATIO)

    @property
    def name(self) -> str:
        return f"{self.chunker}-{self.chunk_size}"


@dataclass
class Chunk:
    document_id: str
    filename: str
    page: int
    page_count: int
    text: str


@dataclass
class PdfFile:
    filename: str
    document_id: str  # SHA-256 of the file, exactly like the app
    pages: list[tuple[int, str]]  # (page number, text)


def load_pdfs() -> list[PdfFile]:
    """Read every PDF in eval/data once (reading pages is free; only embedding costs quota)."""
    pdfs = []
    for path in sorted(DATA_DIR.glob("*.pdf")):
        data = path.read_bytes()
        pdfs.append(PdfFile(path.name, compute_document_id(data), read_pdf_pages(data)))
    return pdfs


def split_page(text: str, setup: Setup) -> list[str]:
    if setup.chunker == "ours":
        return split_text(text, setup.chunk_size, setup.overlap)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=setup.chunk_size, chunk_overlap=setup.overlap
    )
    return splitter.split_text(text)


def make_chunks(pdfs: list[PdfFile], setup: Setup) -> list[Chunk]:
    return [
        Chunk(pdf.document_id, pdf.filename, page_number, len(pdf.pages), text)
        for pdf in pdfs
        for page_number, page_text in pdf.pages
        for text in split_page(page_text, setup)
    ]
