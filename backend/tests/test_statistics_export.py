"""The breakdown, written to a file.

This is the second place data leaves the system, and the less obvious one: the row
exporter next door hands over the table, while this hands over a *conclusion* somebody
is about to paste into a report. So the checks here are about the figures arriving
intact and in a form the receiving program understands - a count Excel can sum, a
percentage it can chart, Hebrew and Arabic that survive the trip.

The binary formats are opened rather than sniffed. An xlsx is a zip of XML, which the
standard library can read, so there is no reason to settle for asserting that the file
begins with "PK" when the actual cell values are two lines away.
"""

import csv
import io
import typing
import xml.etree.ElementTree as ET
import zipfile

import pytest
from app.models.schemas import StatisticsExportRequest, StatisticsExportRow
from app.services import statistics_export as se

HEBREW = "קיה ישראל"
ARABIC = "المجموع"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def request(fmt: str, **over) -> StatisticsExportRequest:
    """A small breakdown of the shape the statistics screen produces."""
    body = dict(
        format=fmt,
        title="פילוח יצרנים",
        subtitle="2018-2023",
        headers=["יצרן", "כמות", "אחוז"],
        rows=[
            StatisticsExportRow(label=HEBREW, count=40, percentage=40.0),
            StatisticsExportRow(label="טויוטה", count=35, percentage=35.0),
            StatisticsExportRow(label="", count=25, percentage=25.0),
        ],
        total_label=ARABIC,
        total=100,
    )
    body.update(over)
    return StatisticsExportRequest(**body)


# ---- csv ---------------------------------------------------------------------------


def csv_rows(payload: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline="")))


def test_the_csv_leads_with_a_byte_order_mark():
    """Without it Excel opens a UTF-8 file as the local codepage and every Hebrew label
    becomes mojibake - the one failure that looks like a data problem rather than a
    file-format one, because the numbers beside it are still right."""
    payload = se.build(request("csv"))
    assert payload.startswith(b"\xef\xbb\xbf")
    assert HEBREW in payload.decode("utf-8-sig")


def test_the_csv_repeats_the_heading_the_screen_showed():
    rows = csv_rows(se.build(request("csv")))
    assert rows[0] == ["פילוח יצרנים"]
    assert rows[1] == ["2018-2023"]
    assert rows[2] == []  # a blank line before the table, as on screen
    assert rows[3] == ["יצרן", "כמות", "אחוז"]


def test_a_breakdown_with_no_heading_starts_at_the_column_names():
    """Both title and subtitle are optional, and dropping them must not leave the blank
    separator behind - a file whose first row is empty is one Excel imports crookedly."""
    rows = csv_rows(se.build(request("csv", title="", subtitle="")))
    assert rows[0] == ["יצרן", "כמות", "אחוז"]


def test_the_csv_carries_every_row_and_then_the_total():
    rows = csv_rows(se.build(request("csv")))
    body = rows[4:]
    assert body[0] == [HEBREW, "40", "40.00"]
    assert body[1] == ["טויוטה", "35", "35.00"]
    assert body[2] == ["", "25", "25.00"]
    assert body[3] == [ARABIC, "100", ""]


def test_the_percentage_is_written_to_two_places():
    """A third of the file is 33.333...; printed raw it runs to seventeen digits and the
    column stops lining up."""
    req = request("csv", rows=[StatisticsExportRow(label="x", count=1, percentage=100 / 3)])
    assert csv_rows(se.build(req))[4] == ["x", "1", "33.33"]


# ---- xlsx --------------------------------------------------------------------------


def workbook(payload: bytes) -> tuple[dict[str, object], ET.Element]:
    """Cell values keyed by reference, plus the sheet element for its own attributes.

    Shared strings are resolved here rather than asserted on: xlsxwriter stores every
    string in a side table and leaves an index in the cell, so a test that read the cell
    alone would be comparing numbers to labels.
    """
    z = zipfile.ZipFile(io.BytesIO(payload))
    strings = [
        "".join(t.text or "" for t in si.iter(f"{NS}t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{NS}si")
    ]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    values: dict[str, object] = {}
    for cell in sheet.iter(f"{NS}c"):
        v = cell.find(f"{NS}v")
        if v is None or v.text is None:
            continue
        values[cell.get("r")] = strings[int(v.text)] if cell.get("t") == "s" else float(v.text)
    return values, sheet


def test_the_workbook_is_a_real_one_and_opens_right_to_left():
    """The data is Hebrew and the interface is Arabic; a sheet that opens with column A
    on the left puts the labels at the far end of the reading direction."""
    payload = se.build(request("xlsx"))
    assert payload[:2] == b"PK"
    _, sheet = workbook(payload)
    view = sheet.find(f"{NS}sheetViews/{NS}sheetView")
    assert view.get("rightToLeft") == "1"


def test_counts_are_stored_as_numbers_rather_than_text():
    """Written as text they cannot be summed, sorted or charted, and Excel marks every
    cell with the green triangle that makes a report look broken."""
    values, _ = workbook(se.build(request("xlsx")))
    assert values["B5"] == 40
    assert values["B6"] == 35
    assert isinstance(values["B5"], float)


def test_the_percentage_is_stored_as_a_fraction_so_excel_can_format_it():
    """40% is the number 0.4 carrying a percentage format, not the number 40 and not the
    text "40%". Storing 40 makes the cell read 4000% the moment anyone reformats it."""
    values, _ = workbook(se.build(request("xlsx")))
    assert values["C5"] == pytest.approx(0.40)
    assert values["C6"] == pytest.approx(0.35)


def test_the_labels_arrive_as_written():
    values, _ = workbook(se.build(request("xlsx")))
    assert values["A5"] == HEBREW
    assert values["A1"] == "פילוח יצרנים"


def test_the_total_row_closes_the_sheet():
    values, _ = workbook(se.build(request("xlsx")))
    assert values["A8"] == ARABIC
    assert values["B8"] == 100
    assert "C8" not in values  # no percentage on the total: it is 100 by construction


# ---- pdf ---------------------------------------------------------------------------


def test_the_pdf_is_a_complete_document():
    payload = se.build(request("pdf"))
    assert payload.startswith(b"%PDF-")
    assert b"%%EOF" in payload[-1024:]


def test_right_to_left_text_is_reshaped_and_reordered_before_it_is_drawn():
    """reportlab draws glyphs in the order it is given them, so Arabic handed over as
    typed comes out disconnected and backwards. U+FEE3 is the joined form of meem that
    the reshaper produces for a word like this one - its presence is the evidence that
    the text was shaped rather than passed straight through.
    """
    drawn = se._rtl("محمد")
    assert 0xFEE3 in [ord(c) for c in drawn]
    assert drawn != "محمد"


def test_presentation_never_breaks_an_export():
    """A label that is not a string at all is a caller's bug, not a reason to fail the
    download the user is waiting for."""
    assert se._rtl(None) == ""
    assert se._rtl(7) == "7"


# ---- across the formats ------------------------------------------------------------


def test_every_format_the_schema_accepts_has_a_media_type():
    """These two lists live in different files. If a fourth format is ever added and this
    one is forgotten, the endpoint raises KeyError while building the response headers -
    after the file has already been generated."""
    allowed = set(typing.get_args(StatisticsExportRequest.model_fields["format"].annotation))
    assert allowed == set(se.MEDIA_TYPES)


@pytest.mark.parametrize("fmt", ["csv", "xlsx", "pdf"])
def test_a_breakdown_with_no_rows_still_produces_a_file(fmt):
    """Every filter combination can end in zero matches, and the export button does not
    grey itself out when it does."""
    payload = se.build(request(fmt, rows=[], total=0))
    assert len(payload) > 0


# ---- through the endpoint ----------------------------------------------------------


def post(client, dataset_id, **body):
    return client.post(f"/api/datasets/{dataset_id}/statistics/export", json=body)


def test_the_endpoint_returns_the_file_on_the_same_request(admin, dataset):
    """No job, no polling, nothing left in the exports folder - unlike a row export."""
    r = post(admin, dataset, format="csv", title="t", rows=[], total=0)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith(b"\xef\xbb\xbf")


def test_the_filename_keeps_the_title_in_its_own_script(admin, dataset):
    """Two names in one header: an ASCII one every client can parse, and the real title
    percent-encoded for the ones that can."""
    r = post(admin, dataset, format="xlsx", title=ARABIC, rows=[], total=0)
    disposition = r.headers["content-disposition"]
    assert 'filename="statistics.xlsx"' in disposition
    assert "filename*=UTF-8''" in disposition
    assert "%D8" in disposition  # the Arabic title, percent-encoded


def test_exporting_a_breakdown_needs_a_session(anon, dataset):
    assert post(anon, dataset, format="csv", rows=[], total=0).status_code == 401
