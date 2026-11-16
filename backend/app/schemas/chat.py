"""Shapes of the data sent to and returned by POST /chat."""

from typing import Annotated

from pydantic import BaseModel, StringConstraints

# Leading/trailing spaces are removed; an empty question is rejected automatically (422).
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChatRequest(BaseModel):
    question: Question


class Source(BaseModel):
    document_id: str
    filename: str
    page: int
    # Similarity between the question and this page's best used chunk:
    # 1 - cosine distance, so 1.0 = same meaning and higher is more relevant.
    score: float


class ChatResponse(BaseModel):
    answer: str
    found: bool  # False when the answer is "I couldn't find this in the documents"
    sources: list[Source]
