"""The only file that talks to ChromaDB."""

from dataclasses import dataclass
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_settings


@dataclass
class StoredChunk:
    """A chunk of text ready to be saved, with its embedding already computed."""

    id: str
    text: str
    embedding: list[float]
    document_id: str
    filename: str
    page: int
    page_count: int


@dataclass
class SearchResult:
    """A chunk found by a search, with its distance from the question."""

    text: str
    document_id: str
    filename: str
    page: int
    # Cosine distance between the question and this chunk:
    # 0 = same meaning, 1 = unrelated, 2 = opposite meaning. Smaller is better.
    distance: float


@dataclass
class DocumentInfo:
    document_id: str
    filename: str
    pages: int
    chunks: int


class VectorStore:
    def __init__(self, path: str, collection_name: str):
        client = chromadb.PersistentClient(
            path=path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # embedding_function=None: Chroma must never create embeddings itself
        # (and never download its default model). We always pass Gemini embeddings.
        # space="cosine": distances are measured by the angle between vectors,
        # which compares meaning and ignores vector length.
        self._collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )

    def add_chunks(self, chunks: list[StoredChunk]) -> None:
        self._collection.add(
            ids=[c.id for c in chunks],
            embeddings=[c.embedding for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "document_id": c.document_id,
                    "filename": c.filename,
                    "page": c.page,
                    "page_count": c.page_count,
                }
                for c in chunks
            ],
        )

    def search(self, query_embedding: list[float], top_k: int) -> list[SearchResult]:
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        # Chroma returns one list per query; we sent one query, so take index [0].
        return [
            SearchResult(
                text=text,
                document_id=meta["document_id"],
                filename=meta["filename"],
                page=meta["page"],
                distance=distance,
            )
            for text, meta, distance in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]

    def document_exists(self, document_id: str) -> bool:
        found = self._collection.get(where={"document_id": document_id}, limit=1, include=[])
        return len(found["ids"]) > 0

    def list_documents(self) -> list[DocumentInfo]:
        """Group all stored chunks by document."""
        all_chunks = self._collection.get(include=["metadatas"])
        documents: dict[str, DocumentInfo] = {}
        for meta in all_chunks["metadatas"]:
            doc_id = meta["document_id"]
            if doc_id not in documents:
                documents[doc_id] = DocumentInfo(
                    document_id=doc_id,
                    filename=meta["filename"],
                    pages=meta["page_count"],
                    chunks=0,
                )
            documents[doc_id].chunks += 1
        return sorted(documents.values(), key=lambda d: d.filename.lower())

    def delete_document(self, document_id: str) -> None:
        self._collection.delete(where={"document_id": document_id})


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return VectorStore(path=str(settings.chroma_path), collection_name=settings.collection_name)
