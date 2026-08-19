"""Finding a font that can draw this data.

The failure this module exists to prevent is a quiet one: reportlab's built-in fonts are
Latin-1, so a PDF of Hebrew data drawn with them opens successfully, prints cleanly, and
contains nothing but black boxes. Nobody gets an error - they get a file they only
discover is useless after sending it on.

So the tests here are less about the happy path than about the two ways the search can
go wrong: choosing a font that cannot draw the scripts, and blowing up when the machine
has no usable font at all. The second is not hypothetical - the CI runner is a bare
Ubuntu image, and whether any of the Linux candidates is installed there decides which
branch these tests take.

The module caches its answer in a process global, which is right for the application and
awkward for tests; every test that changes the search restores it.
"""

import pytest
from app.services import pdf_fonts
from reportlab.pdfbase import pdfmetrics


@pytest.fixture(autouse=True)
def forget_the_cached_answer():
    """Each test starts the search over and leaves the module as it found it."""
    before = pdf_fonts._resolved
    pdf_fonts._resolved = None
    yield
    pdf_fonts._resolved = before


def installed() -> list[str]:
    from pathlib import Path

    return [c for c in pdf_fonts._CANDIDATES if Path(c).is_file()]


def test_the_answer_is_a_font_reportlab_can_actually_use():
    """Whichever branch is taken, the name handed back has to be one reportlab knows -
    returning the path, or a name that was never registered, fails at draw time."""
    name = pdf_fonts.data_font()
    assert name in pdfmetrics.getRegisteredFontNames()


@pytest.mark.skipif(not installed(), reason="no candidate font on this machine")
def test_a_machine_with_fonts_gets_one_that_can_draw_the_data():
    """Not Helvetica: this data is Hebrew, and the whole point of the search is to avoid
    falling back to a face that renders it as boxes."""
    assert pdf_fonts.data_font() == pdf_fonts._REGISTERED_NAME


def test_the_search_runs_once_and_the_answer_is_reused(monkeypatch):
    """data_font() is called for every label of every PDF. Re-reading font files each
    time would make the cost of the search proportional to the size of the table."""
    first = pdf_fonts.data_font()
    monkeypatch.setattr(pdf_fonts, "_CANDIDATES", ("/nowhere/at/all.ttf",))
    assert pdf_fonts.data_font() == first  # the bad candidate list is never consulted


def test_with_no_font_installed_latin_exports_still_work(monkeypatch, caplog):
    """The export must not fail. A Latin-only PDF is a smaller loss than no PDF, and the
    log line is what stops a box-filled page from being an unexplained mystery later."""
    monkeypatch.setattr(pdf_fonts, "_CANDIDATES", ())
    with caplog.at_level("WARNING"):
        assert pdf_fonts.data_font() == pdf_fonts.FALLBACK
    assert "boxes" in caplog.text


def test_an_unreadable_file_is_skipped_rather_than_raising(monkeypatch, tmp_path, caplog):
    """Font directories collect broken things: truncated downloads, .ttf names on files
    that are not fonts. One of them must not take the export down with it."""
    junk = tmp_path / "broken.ttf"
    junk.write_bytes(b"this is not a font")
    monkeypatch.setattr(pdf_fonts, "_CANDIDATES", (str(junk),))
    with caplog.at_level("WARNING"):
        assert pdf_fonts.data_font() == pdf_fonts.FALLBACK


def test_coverage_is_read_from_the_font_rather_than_assumed_from_its_name(tmp_path):
    """"Arial" is a different file on every machine. A font is only credited with a
    script if its character map actually contains the probe."""
    junk = tmp_path / "notafont.ttf"
    junk.write_bytes(b"\x00\x01\x02")
    assert pdf_fonts._covers(junk) == set()

    for candidate in installed():
        from pathlib import Path

        covered = pdf_fonts._covers(Path(candidate))
        assert "latin" in covered, candidate
        break


@pytest.mark.skipif(not installed(), reason="no candidate font on this machine")
def test_the_chosen_font_covers_more_than_latin():
    """A face that only has Latin is worse than useless here - it would be selected,
    registered, and then draw the Hebrew as boxes anyway. The search scores candidates by
    how many scripts they cover, so on a machine with real fonts the winner should carry
    at least one of the two right-to-left scripts.
    """
    from pathlib import Path

    best = max(len(pdf_fonts._covers(Path(c))) for c in installed())
    assert best > 1, "no installed candidate covers Arabic or Hebrew"


def test_the_arabic_probe_is_the_shape_the_reshaper_actually_produces():
    """U+FEE3 rather than plain meem, and not by accident: statistics_export runs text
    through arabic_reshaper before drawing it, which converts letters to their joined
    presentation forms. A font can carry every plain Arabic letter and still lack those,
    so probing with the plain form would approve a font that cannot draw the output.
    """
    import arabic_reshaper

    assert pdf_fonts._PROBES["arabic"] == 0xFEE3
    shaped = arabic_reshaper.reshape("محمد")
    assert pdf_fonts._PROBES["arabic"] in [ord(c) for c in shaped]


def test_the_hebrew_probe_is_a_letter_the_data_is_full_of():
    """Aleph. Every Hebrew manufacturer name in the registry contains one."""
    assert chr(pdf_fonts._PROBES["hebrew"]) == "א"
