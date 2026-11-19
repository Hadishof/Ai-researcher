"""Tests for reading text out of a PDF (no API, no database)."""

from app.services.ingestion import read_pdf_pages


def test_ligatures_are_replaced_by_plain_letters(make_pdf):
    # "ﬁ" is ONE character (U+FB01), as PDFs often store "fi". Without NFKC
    # normalization, the text would say "ﬁlter", which is not the word "filter".
    data = make_pdf(["Replace the carbon ﬁlter every 6 months."])

    [(page_number, text)] = read_pdf_pages(data)

    assert page_number == 1
    assert "filter" in text
    assert "ﬁ" not in text


def test_hebrew_text_is_unchanged_by_normalization(make_pdf):
    data = make_pdf(["ימי חופשה לעובדים"])

    [(_, text)] = read_pdf_pages(data)

    assert "ימי חופשה לעובדים" in text
