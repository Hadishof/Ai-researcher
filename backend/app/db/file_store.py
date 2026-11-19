"""The only file that reads and writes the original PDF files on disk."""

import re
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

# A document id is the SHA-256 hash of the file: exactly 64 lowercase hex characters.
DOCUMENT_ID = re.compile(r"^[0-9a-f]{64}$")


class FileStore:
    """
    Saves each uploaded PDF as <folder>/<document_id>.pdf.

    The path is built ONLY from the document id, and the id is checked first: 64 hex
    characters can't contain "/", "\\" or "..", so a path can never point outside the
    folder. The uploaded filename is never part of a path (it's only a label).
    """

    def __init__(self, folder: Path):
        self.folder = folder

    def path(self, document_id: str) -> Path:
        if not DOCUMENT_ID.fullmatch(document_id):
            raise ValueError("Invalid document id.")
        return self.folder / f"{document_id}.pdf"

    def save(self, document_id: str, data: bytes) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path(document_id).write_bytes(data)

    def exists(self, document_id: str) -> bool:
        return self.path(document_id).is_file()

    def delete(self, document_id: str) -> None:
        self.path(document_id).unlink(missing_ok=True)  # no file is fine: nothing to delete


@lru_cache
def get_file_store() -> FileStore:
    return FileStore(get_settings().files_path)
