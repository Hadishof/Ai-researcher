"""Loads the evaluation questions from eval/data/dataset.jsonl and checks that every row is valid."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

DATA_DIR = Path(__file__).resolve().parent / "data"
DATASET_PATH = DATA_DIR / "dataset.jsonl"

Language = Literal["en", "he"]
QuestionType = Literal[
    "factual", "distractor", "cross_lingual", "not_found", "follow_up", "conflict"
]


class ExpectedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    page: int


class HistoryMessage(BaseModel):
    """An earlier message in the chat, for follow-up questions."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str


class Question(BaseModel):
    """One evaluation question. Each one runs as if in its own chat."""

    # extra="forbid": a misspelled field name (e.g. "expected_fact") is an error,
    # instead of being silently ignored.
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    language: Language
    type: QuestionType
    documents: list[str]  # filenames the chat selects; only these are searched
    expect_found: bool
    expected_pages: list[ExpectedPage]
    require_all_pages: bool  # true for conflicts: every expected page must be used
    # Each inner list is one fact, with its acceptable spellings, e.g. [["1,500", "1500"], ["hour"]].
    # The answer must contain one spelling of EVERY fact.
    expected_facts: list[list[str]]
    history: list[HistoryMessage]
    note: str = ""

    @model_validator(mode="after")
    def check_consistency(self) -> "Question":
        """Rules that connect fields, so a mistake in the data is caught before a run."""
        if not self.documents:
            raise ValueError("documents must not be empty")
        for page in self.expected_pages:
            if page.file not in self.documents:
                raise ValueError(f"expected page file {page.file!r} is not in documents")
        if self.expect_found != bool(self.expected_pages):
            raise ValueError("expected_pages must be given exactly when expect_found is true")
        if self.expect_found != bool(self.expected_facts):
            raise ValueError("expected_facts must be given exactly when expect_found is true")
        if any(not group for group in self.expected_facts):
            raise ValueError("every fact group needs at least one acceptable spelling")
        if (self.type == "not_found") == self.expect_found:
            raise ValueError("expect_found must be false exactly for not_found questions")
        if (self.type == "follow_up") != bool(self.history):
            raise ValueError("history must be given exactly for follow_up questions")
        if (self.type == "conflict") != self.require_all_pages:
            raise ValueError("require_all_pages must be true exactly for conflict questions")
        return self


def load_dataset(path: Path = DATASET_PATH) -> list[Question]:
    """Read one JSON object per line. Stops with the line number if a row is invalid."""
    questions: list[Question] = []
    seen_ids: set[str] = set()
    with open(path, encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                question = Question.model_validate(json.loads(line))
            except (json.JSONDecodeError, ValidationError) as error:
                raise ValueError(f"{path.name} line {line_number}: {error}") from None
            if question.id in seen_ids:
                raise ValueError(f"{path.name} line {line_number}: duplicate id {question.id!r}")
            missing = [name for name in question.documents if not (path.parent / name).is_file()]
            if missing:
                raise ValueError(f"{path.name} line {line_number}: missing PDF(s) {missing}")
            seen_ids.add(question.id)
            questions.append(question)
    return questions
