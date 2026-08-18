"""Exports.

An export is the point where the data leaves the system, so a defect here is the one the
user carries away in a file and finds out about later. The CSV path is checked by reading
the downloaded bytes back and comparing them to the source file; the binary formats are
checked for the properties that can be verified without reimplementing their readers.
"""

import csv
import io

import synthetic
from conftest import wait_for_job
from helpers import rows_as_dicts


def download(client, dataset_id, **request) -> bytes:
    request.setdefault("source", "raw")
    r = client.post(f"/api/datasets/{dataset_id}/export", json=request)
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "done", job

    r = client.get(f"/api/datasets/{dataset_id}/export/{job_id}/download")
    assert r.status_code == 200, r.text
    return r.content


def read_csv(payload: bytes) -> list[dict]:
    text = payload.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def test_csv_export_round_trips_every_row(admin, dataset, oracle):
    """Out and back with nothing lost: same row count, same columns, same cells."""
    rows = read_csv(download(admin, dataset, format="csv"))
    assert len(rows) == len(oracle)
    assert list(rows[0].keys()) == synthetic.COLUMNS

    by_id = {}
    for r in rows:
        by_id.setdefault(r["mispar_rechev"], []).append(r)
    for source in oracle:
        exported = by_id[source["mispar_rechev"]]
        assert any(
            all((e[c] or "") == (source[c] or "") for c in synthetic.COLUMNS) for e in exported
        ), source["mispar_rechev"]


def test_csv_export_preserves_leading_zeros(admin, dataset):
    """The identifier has to survive the last hop too. An export that renders it as 42 has
    destroyed it just as thoroughly as an import that did.
    """
    rows = read_csv(download(admin, dataset, format="csv"))
    ids = {r["mispar_rechev"] for r in rows}
    assert "00009042" in ids


def test_csv_export_is_readable_as_utf8_with_hebrew_intact(admin, dataset):
    payload = download(admin, dataset, format="csv")
    text = payload.decode("utf-8-sig")
    assert synthetic.KIA in text
    assert "�" not in text


def test_csv_export_requotes_the_awkward_fields(admin, dataset):
    """A comma, a quote and a newline inside values, re-serialized into a comma-delimited
    file. If quoting is wrong here the file silently gains columns or rows when opened.
    """
    rows = read_csv(download(admin, dataset, format="csv"))
    found = {r["mispar_rechev"]: r for r in rows}
    assert found["00009043"]["tzeva_rechev"] == "שחור, מטאלי"
    assert found["00009044"]["tzeva_rechev"] == 'גלגלי 15" אלומיניום'
    assert found["00009045"]["tzeva_rechev"] == "כסף\nבהיר"
    # nothing shifted into the next column
    assert found["00009043"]["ramat_gimur"] == "EX"


def test_export_of_the_current_view_matches_what_the_grid_shows(admin, dataset, oracle):
    """The promise of "export what I am looking at": same filter, same search, same rows.
    """
    request = {
        "format": "csv",
        "scope": "current_view",
        "source": "raw",
        "filters": [{"column": "sug_delek_nm", "op": "eq", "value": "דיזל"}],
    }
    exported = read_csv(download(admin, dataset, **request))
    on_screen = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "sug_delek_nm", "op": "eq", "value": "דיזל"}],
    )
    assert len(exported) == len(on_screen)
    assert {r["mispar_rechev"] for r in exported} == {r["mispar_rechev"] for r in on_screen}


def test_export_of_everything_ignores_the_view(admin, dataset, oracle):
    request = {
        "format": "csv",
        "scope": "all",
        "source": "raw",
        "filters": [{"column": "sug_delek_nm", "op": "eq", "value": "דיזל"}],
    }
    exported = read_csv(download(admin, dataset, **request))
    assert len(exported) == len(oracle)


def test_exporting_the_current_view_honours_its_sort(admin, dataset):
    exported = read_csv(
        download(admin, dataset, format="csv", scope="current_view",
                 sort_by="mispar_rechev", sort_dir="desc")
    )
    ids = [r["mispar_rechev"] for r in exported]
    assert ids == sorted(ids, reverse=True)


def test_exporting_everything_is_served_in_table_order(admin, dataset):
    """Deliberate, and pinned here so it does not get "fixed" by accident: a whole-file
    export ignores sort_by. Ordering 4.1M rows costs a full sort for an output nobody
    reads top-down, and "all" means the file as it was imported. Sorting belongs to the
    view, which is what current_view exports.
    """
    exported = read_csv(
        download(admin, dataset, format="csv", scope="all",
                 sort_by="mispar_rechev", sort_dir="desc")
    )
    ids = [r["mispar_rechev"] for r in exported]
    assert ids != sorted(ids, reverse=True)
    assert ids == [r["mispar_rechev"] for r in read_csv(download(admin, dataset, format="csv"))]


def test_xlsx_export_is_a_real_workbook(admin, dataset):
    """Verified by its container signature rather than by parsing it: a truncated or
    empty file is the realistic failure, and that is what this catches.
    """
    payload = download(admin, dataset, format="xlsx")
    assert payload[:2] == b"PK"  # zip container, which is what xlsx is
    assert len(payload) > 2000


def test_pdf_export_is_a_real_pdf(admin, dataset):
    payload = download(admin, dataset, format="pdf")
    assert payload.startswith(b"%PDF-")
    assert b"%%EOF" in payload[-1024:]


def test_an_unknown_format_is_refused(admin, dataset):
    r = admin.post(f"/api/datasets/{dataset}/export", json={"format": "docx", "source": "raw"})
    assert r.status_code == 422, r.text


def test_downloading_an_unknown_job_is_a_404(admin, dataset):
    r = admin.get(f"/api/datasets/{dataset}/export/no-such-job/download")
    assert r.status_code == 404, r.text
