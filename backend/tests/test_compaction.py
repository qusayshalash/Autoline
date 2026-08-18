"""Compaction.

This is the only operation in the project that replaces a data file rather than adding
to one, so the tests are mostly about what happens when it goes wrong: a verification
that fails must leave the original exactly as it was, and no failure path may end with
the dataset having no file at all.
"""

import duckdb
import pytest
import synthetic
from app.db.connection import datasets
from app.services import compaction
from helpers import rows_as_dicts, total


@pytest.fixture
def own(admin, csv_path) -> str:
    """A dataset of this test's own, since compaction replaces the file underneath it."""
    from conftest import wait_for_job

    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("compact.csv", f, "text/csv")})
    ds = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{ds}/import",
        json={"encoding": synthetic.ENCODING, "delimiter": synthetic.DELIMITER,
              "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    return ds


def bloat(dataset_id: str) -> int:
    """Leaves real free space inside the file, the way ordinary use does.

    A 489-row fixture is far too small to accumulate anything measurable through normal
    cleaning runs, so the pages are written explicitly: a large table created and then
    dropped leaves exactly the condition compaction exists for - a file much bigger than
    the data still in it. Returns the inflated size.
    """
    with datasets.write_lock(dataset_id):
        cur = datasets.cursor(dataset_id)
        cur.execute(
            "CREATE TABLE ballast AS "
            "SELECT i AS n, repeat('x', 200) AS pad FROM range(300000) t(i)"
        )
        cur.execute("CHECKPOINT")
        cur.execute("DROP TABLE ballast")
        cur.execute("CHECKPOINT")
    return datasets.path_for(dataset_id).stat().st_size


def test_compaction_preserves_every_row(admin, own, oracle):
    before = rows_as_dicts(admin, own, source="raw", sort_by="mispar_rechev")
    compaction.compact(own)
    after = rows_as_dicts(admin, own, source="raw", sort_by="mispar_rechev")

    assert len(after) == len(oracle)
    assert after == before


def test_compaction_reclaims_the_free_space(admin, own, oracle):
    """The whole point, measured: a file inflated to many times its content shrinks back,
    and still holds every row afterwards."""
    inflated = bloat(own)
    result = compaction.compact(own)

    assert result.skipped is False, "an inflated file should have been worth compacting"
    assert result.bytes_before == inflated
    assert result.bytes_after < result.bytes_before
    assert result.freed_bytes == result.bytes_before - result.bytes_after
    # a proportion rather than a byte count: how much a given version of DuckDB leaves
    # behind is its business, and an absolute figure here would be a fixture detail
    # masquerading as a requirement. The requirement is that the file gets meaningfully
    # smaller - at least as much as the threshold that made it worth running at all.
    assert result.bytes_after <= result.bytes_before / compaction.MIN_WORTHWHILE_RATIO
    assert result.tables["raw_data"] == len(oracle)
    assert total(admin, own, source="raw") == len(oracle)


def test_the_dataset_still_works_afterwards(admin, own, oracle):
    """The connection pool holds the file open, so a swap that did not close and reopen
    it correctly would leave every later query reading a deleted file."""
    bloat(own)
    compaction.compact(own)

    assert total(admin, own, source="raw") == len(oracle)
    assert admin.post(
        f"/api/datasets/{own}/statistics", json={"group_by": "baalut", "source": "raw"}
    ).status_code == 200
    # and it is still writable
    assert admin.post(f"/api/datasets/{own}/clean", json={"dedupe": True}).status_code == 200


def test_hebrew_and_padded_identifiers_survive(admin, own):
    compaction.compact(own)
    rows = rows_as_dicts(
        admin, own, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009042"}],
    )
    assert rows[0]["mispar_rechev"] == "00009042"
    assert rows[0]["tozeret_nm"] == synthetic.KIA


def test_an_already_compact_file_is_left_alone(admin, own):
    """Compaction of a file with nothing to reclaim must not rewrite it for the sake of
    it - and must say so rather than reporting a saving of zero as a success."""
    compaction.compact(own)  # first pass does whatever there is to do
    second = compaction.compact(own)
    assert second.skipped is True
    assert second.freed_bytes == 0
    assert second.reason


def test_a_failed_verification_leaves_the_original_untouched(admin, own, oracle, monkeypatch):
    """The important one. If the rewritten file cannot be read back, the original must
    still be there, still complete, and still the file the dataset is using.
    """
    original = datasets.path_for(own)
    size_before = original.stat().st_size

    monkeypatch.setattr(
        compaction, "_verify_against", lambda path, expected: ["simulated corruption"]
    )
    with pytest.raises(RuntimeError, match="unusable"):
        compaction.compact(own)

    assert original.exists()
    assert original.stat().st_size == size_before
    assert total(admin, own, source="raw") == len(oracle)


def test_a_failed_run_leaves_no_temporary_files_behind(admin, own, monkeypatch):
    original = datasets.path_for(own)
    monkeypatch.setattr(compaction, "_verify_against", lambda path, expected: ["nope"])
    with pytest.raises(RuntimeError):
        compaction.compact(own)

    assert not original.with_suffix(".compacting.duckdb").exists()
    assert not original.with_suffix(".old.duckdb").exists()


def test_verification_detects_a_missing_table(own, tmp_path):
    empty = tmp_path / "empty.duckdb"
    duckdb.connect(str(empty)).close()
    errors = compaction._verify_against(empty, {"raw_data": 489})
    assert any("missing" in e for e in errors)


def test_verification_detects_a_wrong_row_count(own, tmp_path):
    path = tmp_path / "short.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute("CREATE TABLE raw_data AS SELECT 1 AS a")
    conn.close()
    errors = compaction._verify_against(path, {"raw_data": 489})
    assert any("expected" in e for e in errors)


def test_verification_detects_an_unreadable_file(own, tmp_path):
    junk = tmp_path / "junk.duckdb"
    junk.write_bytes(b"this is not a database")
    errors = compaction._verify_against(junk, {"raw_data": 1})
    assert errors


def test_the_estimate_reports_the_file_size_without_changing_it(own):
    path = datasets.path_for(own)
    before = path.stat().st_size
    estimate = compaction.estimate(own)
    assert estimate["file_bytes"] == before
    assert estimate["tables"]["raw_data"] > 0
    assert path.stat().st_size == before


# ---- through the API ---------------------------------------------------------------


def test_an_admin_can_compact_through_the_api(admin, own, oracle):
    from conftest import wait_for_job

    bloat(own)
    r = admin.post(f"/api/admin/datasets/{own}/compaction")
    assert r.status_code == 200, r.text
    job = wait_for_job(admin, r.json()["id"])
    assert job["status"] == "done", job
    assert total(admin, own, source="raw") == len(oracle)


def test_compacting_an_unknown_dataset_is_a_404(admin):
    assert admin.post("/api/admin/datasets/no-such-dataset/compaction").status_code == 404
    assert admin.get("/api/admin/datasets/no-such-dataset/compaction").status_code == 404


def test_a_viewer_cannot_compact(viewer, own):
    assert viewer.post(f"/api/admin/datasets/{own}/compaction").status_code == 403
    assert viewer.get(f"/api/admin/datasets/{own}/compaction").status_code == 403


def test_an_editor_cannot_compact(editor, own):
    """Same rule as deleting a dataset: the operation that replaces a file needs the
    permission that covers losing one."""
    assert editor.post(f"/api/admin/datasets/{own}/compaction").status_code == 403
