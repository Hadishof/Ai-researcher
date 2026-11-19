"""Unit tests for the chunker (split_text): no API, no database, just text in and chunks out."""

from app.services.ingestion import split_text


def shared_start(previous: str, current: str) -> str:
    """The longest text that ends `previous` and also starts `current` (the overlap)."""
    for length in range(min(len(previous), len(current)), 0, -1):
        if previous.endswith(current[:length]):
            return current[:length]
    return ""


def test_short_paragraphs_are_packed_into_one_chunk():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

    assert split_text(text, chunk_size=1000, overlap=0) == [
        "First paragraph.\nSecond paragraph.\nThird paragraph."
    ]


def test_paragraphs_are_kept_whole():
    paragraphs = [
        "The robot arm can lift heavy boxes all day long.",
        "Support answers critical problems within four hours.",
        "Every employee gets twenty vacation days each year.",
    ]
    text = "\n\n".join(paragraphs)

    # Each paragraph fits in a chunk, but two together do not: one paragraph per chunk.
    assert split_text(text, chunk_size=60, overlap=0) == paragraphs


def test_line_breaks_inside_a_paragraph_become_spaces():
    # PDFs break lines in the middle of sentences; the chunker joins them back.
    text = "This sentence was\nbroken over\nthree lines."

    assert split_text(text, chunk_size=1000, overlap=0) == [
        "This sentence was broken over three lines."
    ]


SPEC_PAGE_LINES = [
    "6. AquaPure AP-800 - Specifications",
    "The AP-800 is designed for offices with up to 40 employees.",
    "Capacity 800 liters per day",
    "Weight 38 kg (empty)",
    "Storage tank 20 liters",
    "Price (2026) 7,900 ILS, or leasing at 249 ILS per month",
]


def test_page_without_blank_lines_is_split_at_line_ends():
    # Like real PDF text: no blank lines, a numbered heading and table rows without full stops.
    text = "\n".join(SPEC_PAGE_LINES)

    chunks = split_text(text, chunk_size=100, overlap=0)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100
        # Every chunk is made of whole lines: no table row is cut or glued to another.
        assert all(line in SPEC_PAGE_LINES for line in chunk.split("\n"))
    # No line is lost, and the order is kept.
    assert [line for chunk in chunks for line in chunk.split("\n")] == SPEC_PAGE_LINES


def test_numbered_heading_stays_whole():
    # Sentence splitting alone would cut "6." off as its own "sentence".
    chunks = split_text("\n".join(SPEC_PAGE_LINES), chunk_size=100, overlap=0)

    assert chunks[0].startswith("6. AquaPure AP-800 - Specifications")


def test_page_that_fits_is_one_chunk_with_lines_joined():
    text = "\n".join(SPEC_PAGE_LINES)  # about 230 characters

    assert split_text(text, chunk_size=1000, overlap=0) == [" ".join(SPEC_PAGE_LINES)]


def test_line_too_long_for_a_chunk_is_split_at_sentence_ends():
    long_line = "The unit is quiet. It fits under a sink. It needs no power. It is easy to clean."
    text = f"Short heading\n{long_line}"

    chunks = split_text(text, chunk_size=40, overlap=0)

    assert all(len(chunk) <= 40 for chunk in chunks)
    pieces = [piece for chunk in chunks for piece in chunk.split("\n")]
    assert pieces == [
        "Short heading",
        "The unit is quiet.",
        "It fits under a sink.",
        "It needs no power.",
        "It is easy to clean.",
    ]


def test_overlap_starts_at_a_whole_word_after_a_line_break():
    chunks = split_text("\n".join(SPEC_PAGE_LINES), chunk_size=100, overlap=30)

    words = {word for line in SPEC_PAGE_LINES for word in line.split()}
    for previous, current in zip(chunks, chunks[1:]):
        overlap = shared_start(previous, current)
        assert overlap  # the new chunk repeats the end of the previous one
        assert overlap.split()[0] in words  # and starts with a whole word


def test_long_paragraph_is_split_at_sentence_ends():
    sentences = [
        "Nimbus Robotics builds robot arms.",
        "The company was founded in 2015.",
        "Its main office is in Haifa.",
        "It has about two hundred employees.",
    ]
    paragraph = " ".join(sentences)  # one paragraph, longer than chunk_size

    chunks = split_text(paragraph, chunk_size=70, overlap=0)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 70
        # Every chunk is made of whole sentences only.
        assert all(part in sentences for part in chunk.split("\n"))
    # No sentence is lost.
    assert [s for chunk in chunks for s in chunk.split("\n")] == sentences


def test_very_long_sentence_is_cut_at_spaces():
    words = [f"word{number:02d}" for number in range(40)]
    sentence = " ".join(words)  # 279 characters, no sentence break anywhere

    chunks = split_text(sentence, chunk_size=50, overlap=0)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 50
        # Cut only at spaces: every piece is a whole word.
        assert all(word in words for word in chunk.split())
    # All words are still there, in the same order.
    assert " ".join(chunks).split() == words


def test_new_chunk_starts_with_the_end_of_the_previous_one():
    sentences = [f"This is sentence number {number} of the test." for number in range(1, 9)]
    text = " ".join(sentences)

    chunks = split_text(text, chunk_size=120, overlap=40)

    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:]):
        overlap = shared_start(previous, current)
        # The repeated part is real (at least one whole word) and not longer than allowed.
        assert len(overlap.split()) >= 1
        assert len(overlap) <= 40
        assert len(current) <= 120


def test_no_overlap_when_overlap_is_zero():
    sentences = [f"This is sentence number {number} of the test." for number in range(1, 9)]

    chunks = split_text(" ".join(sentences), chunk_size=120, overlap=0)

    # Every sentence appears exactly once across all chunks.
    assert [s for chunk in chunks for s in chunk.split("\n")] == sentences


def test_hebrew_text_is_split_at_sentence_ends():
    sentences = [
        "העובדים מקבלים עשרים ימי חופשה בשנה.",
        "יש לאשר את החופשה מראש אצל המנהל.",
        "ימי מחלה אינם נספרים כימי חופשה.",
        "אפשר להעביר עד חמישה ימים לשנה הבאה.",
    ]
    paragraph = " ".join(sentences)

    chunks = split_text(paragraph, chunk_size=80, overlap=0)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 80
        assert all(part in sentences for part in chunk.split("\n"))
    assert [s for chunk in chunks for s in chunk.split("\n")] == sentences


def test_empty_text_gives_no_chunks():
    assert split_text("", chunk_size=100, overlap=10) == []
    assert split_text("   \n\n  \n", chunk_size=100, overlap=10) == []
