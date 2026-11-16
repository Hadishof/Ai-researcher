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
