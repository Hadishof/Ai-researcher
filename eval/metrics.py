"""
Scoring functions for the evaluation. Pure functions: no Gemini, no database, no files.

A page is identified by (filename, page_number), e.g. ("Manual.pdf", 3).
"""

import re
import unicodedata

Page = tuple[str, int]

# A comma between digits that is followed by exactly three digits: "1,500" -> "1500".
# "1,2,3" (a list) is left alone, because only one digit follows each comma.
THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
WHITESPACE = re.compile(r"\s+")


# ---------- Retrieval ----------


def unique_pages(pages: list[Page]) -> list[Page]:
    """
    Remove repeated pages, keeping the first (best ranked) one.

    Search returns chunks, and one page can have several chunks. Ranking pages
    instead of chunks keeps the comparison fair between small chunks (many per
    page) and large chunks (one per page).
    """
    seen: set[Page] = set()
    result = []
    for page in pages:
        if page not in seen:
            seen.add(page)
            result.append(page)
    return result


def first_hit_rank(ranked: list[Page], expected: list[Page]) -> int | None:
    """Position (from 1) of the first expected page in the ranked list, or None if absent."""
    expected_set = set(expected)
    for position, page in enumerate(unique_pages(ranked), 1):
        if page in expected_set:
            return position
    return None


def hit_at_k(ranked: list[Page], expected: list[Page], k: int) -> bool:
    """True if any expected page is among the top k pages."""
    rank = first_hit_rank(ranked, expected)
    return rank is not None and rank <= k


def reciprocal_rank(ranked: list[Page], expected: list[Page]) -> float:
    """1 / position of the first correct page: 1st -> 1.0, 2nd -> 0.5, 3rd -> 0.33, missing -> 0."""
    rank = first_hit_rank(ranked, expected)
    return 1 / rank if rank else 0.0


def pages_found(retrieved: list[Page], expected: list[Page]) -> int:
    """How many of the expected pages appear anywhere in `retrieved` (for conflict questions)."""
    return len(set(expected) & set(retrieved))


# ---------- Answers ----------


def normalize(text: str) -> str:
    """
    Make two texts comparable: "1,500  Liters" == "1500 liters", "ﬁlter" == "filter".

    NFKC replaces special characters with plain ones (the ligature "ﬁ" becomes
    "f" + "i"), then: lowercase, drop thousands separators, collapse spaces.
    """
    text = unicodedata.normalize("NFKC", text)
    text = THOUSANDS_SEPARATOR.sub("", text.casefold())
    return WHITESPACE.sub(" ", text).strip()


def contains_fact(answer: str, spelling: str) -> bool:
    """
    True if `spelling` appears in the answer (after normalizing both).

    A number must not be part of a longer number: "240" does not match "2400",
    and "3 months" does not match "13 months".
    """
    spelling = normalize(spelling)
    pattern = re.escape(spelling)
    if spelling[:1].isdigit():
        pattern = r"(?<!\d)" + pattern
    if spelling[-1:].isdigit():
        pattern = pattern + r"(?!\d)"
    return re.search(pattern, normalize(answer)) is not None


def missing_facts(answer: str, expected_facts: list[list[str]]) -> list[list[str]]:
    """The fact groups for which none of the acceptable spellings is in the answer."""
    return [
        group
        for group in expected_facts
        if not any(contains_fact(answer, spelling) for spelling in group)
    ]


def facts_present(answer: str, expected_facts: list[list[str]]) -> bool:
    """True if the answer contains every fact (one acceptable spelling of each group)."""
    return not missing_facts(answer, expected_facts)


# ---------- Summaries ----------


def average(values: list[float | bool | None]) -> float | None:
    """Mean of the values that apply. None means "not applicable" and is skipped."""
    applicable = [float(value) for value in values if value is not None]
    return sum(applicable) / len(applicable) if applicable else None


def breakdown(records: list[dict], metric: str) -> dict:
    """
    Average one metric overall, by language and by question type.

    Each record is one question's result, e.g.
    {"language": "he", "type": "factual", "hit@1": True}.
    Returns {"overall": {...}, "by_language": {"he": {...}}, "by_type": {...}},
    where each {...} is {"value": average, "count": questions it applies to}.
    """

    def summarize(group: list[dict]) -> dict:
        values = [record.get(metric) for record in group]
        return {
            "value": average(values),
            "count": sum(value is not None for value in values),
        }

    result = {"overall": summarize(records), "by_language": {}, "by_type": {}}
    for field, key in (("language", "by_language"), ("type", "by_type")):
        for name in sorted({record[field] for record in records}):
            result[key][name] = summarize([r for r in records if r[field] == name])
    return result
