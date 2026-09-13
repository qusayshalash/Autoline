"""Exports must not hand a spreadsheet something to execute.

A cell reading =cmd|' /c calc'!A1 is ordinary text in a CSV and ordinary text in this
database. It stops being text the moment a spreadsheet decides otherwise - which the
workbook writer used to do for us, turning an imported value into a live DDE formula
aimed at whoever opened the file.
"""

import csv
import io
import re
import zipfile

import pytest
from conftest import wait_for_job

# The first two are the payloads that matter: one evaluates, one is the documented
# command-execution form. The rest are here to pin what must *not* be quoted.
PAYLOADS = [
    "=1+1",
    "=cmd|' /c calc'!A1",
    "@SUM(1+1)",
    "+1+1",
    "-1+1",
    "\t=1+1",
]
NOT_PAYLOADS = [
    "-4000",        # a negative number, not a formula
    "+1234",        # a signed number
    "-3.5",
    "0",
    "plain text",
    "رام الله",
    "a=b",          # an equals sign that is not in front
]
HEADER = ["value", "note"]


@pytest.fixture(scope="module")
def risky(admin, tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("formula") / "risky.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for i, v in enumerate(PAYLOADS + NOT_PAYLOADS):
            w.writerow([v, f"row{i}"])

    with open(path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("risky.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]

    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert r.status_code == 200, r.text
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    return dataset_id


def export(admin, dataset_id: str, fmt: str) -> bytes:
    r = admin.post(f"/api/datasets/{dataset_id}/export", json={"format": fmt})
    assert r.status_code == 200, r.text
    job = wait_for_job(admin, r.json()["id"])
    assert job["status"] == "done", job
    r = admin.get(f"/api/datasets/{dataset_id}/export/{job['id']}/download")
    assert r.status_code == 200, r.text
    return r.content


# ---- the payloads survive import as text --------------------------------------------

def test_the_payloads_are_stored_as_written(admin, risky):
    """The fix belongs at the export, not the import. What was in the file stays in the
    database exactly as it arrived."""
    r = admin.post(f"/api/datasets/{risky}/data", json={"page_size": 100})
    assert r.status_code == 200, r.text
    data = r.json()
    i = data["columns"].index("value")
    stored = [row[i] for row in data["rows"]]
    for payload in PAYLOADS:
        assert payload in stored, payload


# ---- xlsx ------------------------------------------------------------------------------

def _sheet_xml(blob: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(blob))
    return z.read("xl/worksheets/sheet1.xml").decode("utf-8")


def test_the_workbook_contains_no_live_formula(admin, risky):
    """<f> is the element that makes a cell a formula. There must not be one."""
    sheet = _sheet_xml(export(admin, risky, "xlsx"))
    assert "<f>" not in sheet, re.findall(r"<f>.*?</f>", sheet)[:5]


def test_the_dde_payload_is_written_as_text(admin, risky):
    """The specific value that used to come out executable."""
    blob = export(admin, risky, "xlsx")
    sheet = _sheet_xml(blob)
    assert "cmd|" not in re.sub(r"<f>.*?</f>", "", sheet) or "<f>" not in sheet

    z = zipfile.ZipFile(io.BytesIO(blob))
    everything = "".join(
        z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith(".xml")
    )
    # present somewhere as content, just never as a formula
    assert "calc" in everything


def test_the_workbook_keeps_the_values_unaltered(admin, risky):
    """No apostrophe is added here - the writer is simply told not to reinterpret text,
    so a workbook still reads back exactly what was imported."""
    blob = export(admin, risky, "xlsx")
    z = zipfile.ZipFile(io.BytesIO(blob))
    everything = "".join(
        z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith(".xml")
    )
    assert "=1+1" in everything
    assert "'=1+1" not in everything


def test_a_column_of_addresses_does_not_become_hyperlinks(admin, tmp_path_factory):
    """strings_to_urls off, for the second reason: a sheet may hold only 65,530 link
    objects, so a column of addresses could fail an export outright."""
    path = tmp_path_factory.mktemp("links") / "links.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site"])
        for i in range(50):
            w.writerow([f"http://example.com/{i}"])
    with open(path, "rb") as f:
        up = admin.post("/api/datasets/upload", files={"file": ("links.csv", f, "text/csv")}).json()
    j = admin.post(
        f"/api/datasets/{up['dataset_id']}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    ).json()
    assert wait_for_job(admin, j["id"])["status"] == "done"

    z = zipfile.ZipFile(io.BytesIO(export(admin, up["dataset_id"], "xlsx")))
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "<hyperlink" not in sheet


# ---- csv ---------------------------------------------------------------------------------

def _csv_values(blob: bytes) -> list[str]:
    rows = list(csv.DictReader(io.StringIO(blob.decode("utf-8"))))
    return [r["value"] for r in rows]


def test_every_formula_leading_cell_is_quoted_in_the_csv(admin, risky):
    values = _csv_values(export(admin, risky, "csv"))
    for payload in PAYLOADS:
        assert ("'" + payload) in values, (payload, values)


def test_no_bare_formula_survives_in_the_csv(admin, risky):
    """The property stated without reference to the fixture: nothing a spreadsheet would
    execute may be the first character of a cell, unless the cell is a number."""
    for value in _csv_values(export(admin, risky, "csv")):
        if value[:1] in ("=", "@") or (value[:1] in ("+", "-") and _not_a_number(value)):
            pytest.fail(f"unquoted formula-leading cell: {value!r}")


def _not_a_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return True
    return False


def test_numbers_are_left_alone(admin, risky):
    """The reason this is not a plain prefix check: half the leading characters are also
    how a number is legitimately written, and quoting those would put an apostrophe in
    front of a large part of a numeric column to defend against nothing."""
    values = _csv_values(export(admin, risky, "csv"))
    for number in ("-4000", "+1234", "-3.5", "0"):
        assert number in values, (number, values)
        assert ("'" + number) not in values


def test_ordinary_text_is_left_alone(admin, risky):
    values = _csv_values(export(admin, risky, "csv"))
    for text in ("plain text", "رام الله", "a=b"):
        assert text in values
        assert ("'" + text) not in values


def test_the_row_count_is_unchanged_by_the_quoting(admin, risky):
    rows = list(csv.DictReader(io.StringIO(export(admin, risky, "csv").decode("utf-8"))))
    assert len(rows) == len(PAYLOADS) + len(NOT_PAYLOADS)


def test_a_filtered_csv_export_is_still_neutralised(admin, risky):
    """The projection is built once for the whole query, so it has to survive the
    current_view path as well as the whole-table one."""
    r = admin.post(
        f"/api/datasets/{risky}/export",
        json={"format": "csv", "scope": "current_view",
              "filters": [{"column": "value", "op": "starts_with", "value": "="}]},
    )
    assert r.status_code == 200, r.text
    job = wait_for_job(admin, r.json()["id"])
    assert job["status"] == "done", job
    blob = admin.get(f"/api/datasets/{risky}/export/{job['id']}/download").content
    values = _csv_values(blob)
    assert values, "the filter should have matched the = payloads"
    assert all(v.startswith("'=") for v in values), values


# ---- pdf -------------------------------------------------------------------------------------

def test_the_pdf_export_still_builds(admin, risky):
    """Nothing in a PDF executes, so it is left faithful - this only checks the shared
    query builder did not break it."""
    blob = export(admin, risky, "pdf")
    assert blob[:4] == b"%PDF"
