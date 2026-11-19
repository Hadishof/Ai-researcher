"""Makes a short conversation title from the chat's first question."""

import re

TITLE_MAX_LENGTH = 60
WHITESPACE = re.compile(r"\s+")


def make_title(question: str) -> str:
    """A short conversation title from the first question, cut at a whole word."""
    title = WHITESPACE.sub(" ", question).strip()
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    cut = title.rfind(" ", 0, TITLE_MAX_LENGTH)
    if cut <= TITLE_MAX_LENGTH // 2:  # no space in a sensible place: cut at the limit
        cut = TITLE_MAX_LENGTH
    return title[:cut].rstrip() + "…"
