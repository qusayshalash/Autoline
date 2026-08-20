"""Guard rails around the upload endpoint that are not about CSV correctness.

The disk backing an upload is shared with every other dataset's tables, so what is free
can run out for reasons that have nothing to do with the file being uploaded. Real disk
space cannot be exhausted in a test without either a very large fixture or a very slow
one, so these lower the threshold instead of shrinking the disk - min_free_disk_bytes set
above whatever is actually free makes the guard trip on the very next chunk, which is the
same code path a genuinely full disk would take.
"""

import synthetic
from app.services import ingestion


def test_an_upload_is_refused_once_free_space_runs_low(admin, csv_path, monkeypatch):
    monkeypatch.setattr(ingestion.settings, "min_free_disk_bytes", 2**63 - 1)
    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("toolow.csv", f, "text/csv")})
    assert r.status_code == 413, r.text


def test_the_dataset_is_marked_as_errored_rather_than_left_uploading(admin, csv_path, monkeypatch):
    """The router creates the catalog row before streaming starts, so even a rejected
    upload leaves an id behind - it must not leave that id stuck in "uploading" with no
    way for the interface to explain what happened."""
    monkeypatch.setattr(ingestion.settings, "min_free_disk_bytes", 2**63 - 1)
    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("stuck.csv", f, "text/csv")})
    assert r.status_code == 413, r.text

    listing = admin.get("/api/datasets").json()
    stuck = next(d for d in listing if d["original_filename"] == "stuck.csv")
    assert stuck["status"] == "error"


def test_the_partial_file_does_not_survive_a_rejected_upload(admin, csv_path, monkeypatch, tmp_path):
    monkeypatch.setattr(ingestion.settings, "min_free_disk_bytes", 2**63 - 1)
    before = {p for p in ingestion.settings.uploads_dir.rglob("raw*") if p.is_file()}
    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("leftover.csv", f, "text/csv")})
    assert r.status_code == 413, r.text
    after = {p for p in ingestion.settings.uploads_dir.rglob("raw*") if p.is_file()}
    # Nothing this test's upload wrote is still on disk. Comparing against the
    # before-snapshot rather than asserting an empty directory, since other datasets
    # created earlier in the session legitimately have their own raw files here.
    assert after == before


def test_a_normal_upload_is_unaffected_by_the_guard(admin, csv_path, oracle):
    """The default threshold is far below what CI or a developer machine actually has
    free, so the fixture upload - 489 rows, tens of kilobytes - must succeed exactly as
    it does everywhere else in the suite."""
    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("fine.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["detected_delimiter"] == synthetic.DELIMITER
