"""Backups.

The failure this file exists to prevent is a backup system that reports success and
produces unrestorable files. So nothing here trusts a return value: every test reopens
what was written and reads the data back out of it.
"""

import json
import shutil

import duckdb
import pytest
import synthetic
from app.config import settings
from app.services import backup


@pytest.fixture(autouse=True)
def clean_backup_dir():
    """Each test starts with no backups, and leaves none behind."""
    root = backup.backups_root()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    yield
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def test_a_backup_contains_the_data_and_can_be_read_back(dataset, oracle):
    """The whole point, stated once: after a backup, the rows are retrievable from the
    backup file itself - not from the manifest describing it.
    """
    manifest = backup.run()
    assert manifest["verified"], manifest["errors"]

    item = next(i for i in manifest["items"] if i.get("dataset_id") == dataset)
    path = backup.backups_root() / manifest["name"] / item["file"]

    conn = duckdb.connect(str(path), read_only=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0] == len(oracle)
        value = conn.execute(
            "SELECT tozeret_nm FROM raw_data WHERE mispar_rechev = '00009042'"
        ).fetchone()[0]
        assert value == synthetic.KIA
    finally:
        conn.close()


def test_the_backup_is_taken_while_the_server_holds_the_database_open(dataset, admin):
    """The reason COPY FROM DATABASE is used instead of copying the file. The app keeps a
    read-write handle open for the lifetime of the process; a backup that needed exclusive
    access could only run with the system down.
    """
    assert admin.post(f"/api/datasets/{dataset}/data", json={"source": "raw"}).status_code == 200
    manifest = backup.run()
    assert manifest["verified"], manifest["errors"]
    # and the app still works immediately afterwards
    assert admin.post(f"/api/datasets/{dataset}/data", json={"source": "raw"}).status_code == 200


def test_the_catalog_is_backed_up_with_its_users(dataset):
    """Restoring data without the accounts that reach it is a half restore."""
    manifest = backup.run()
    path = backup.backups_root() / manifest["name"] / "catalog.duckdb"
    conn = duckdb.connect(str(path), read_only=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] >= 1
    finally:
        conn.close()


def test_the_manifest_records_what_was_actually_written(dataset, oracle):
    manifest = backup.run()
    root = backup.backups_root() / manifest["name"]
    stored = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert stored["name"] == manifest["name"]
    for item in stored["items"]:
        assert (root / item["file"]).exists()
    item = next(i for i in stored["items"] if i.get("dataset_id") == dataset)
    assert item["tables"]["raw_data"] == len(oracle)


def test_verification_catches_a_damaged_backup(dataset):
    """A backup is only as good as the check on it, so the check itself is tested by
    breaking a file deliberately and confirming it is reported rather than passed.
    """
    manifest = backup.run()
    assert manifest["verified"]

    victim = backup.backups_root() / manifest["name"] / "catalog.duckdb"
    victim.write_bytes(victim.read_bytes()[: 1024 * 8])  # truncate it

    errors = backup._verify(victim, {"users": 1})
    assert errors, "a truncated database must not verify"

    listed = next(b for b in backup.list_all() if b["name"] == manifest["name"])
    assert listed["intact"] is False


def test_verification_catches_a_row_count_that_does_not_match(dataset):
    manifest = backup.run()
    path = backup.backups_root() / manifest["name"] / "catalog.duckdb"
    errors = backup._verify(path, {"users": 99999})
    assert any("expected" in e for e in errors)


def test_a_missing_table_is_reported(dataset):
    manifest = backup.run()
    path = backup.backups_root() / manifest["name"] / "catalog.duckdb"
    errors = backup._verify(path, {"no_such_table": 1})
    assert any("missing" in e for e in errors)


def test_originals_are_included_only_when_asked_for(dataset):
    without = backup.run(include_originals=False)
    assert not any(i["kind"] == "original" for i in without["items"])

    with_them = backup.run(include_originals=True)
    originals = [i for i in with_them["items"] if i["kind"] == "original"]
    assert originals
    for item in originals:
        path = backup.backups_root() / with_them["name"] / item["file"]
        assert path.exists()
        assert path.stat().st_size == item["bytes"]


def test_retention_keeps_the_newest_and_removes_the_rest(dataset):
    names = [backup.run()["name"] for _ in range(3)]
    # runs inside the same second would collide on the name; assert they did not
    assert len(set(names)) == 3, "backup names must be unique"

    result = backup.prune(keep=2)
    assert result["removed"] == 1
    remaining = [b["name"] for b in backup.list_all()]
    assert sorted(remaining) == sorted(names[-2:])


def test_retention_of_zero_never_deletes_anything(dataset):
    backup.run()
    assert backup.prune(keep=0)["removed"] == 0
    assert len(backup.list_all()) == 1


def test_an_unverified_run_does_not_displace_a_good_one(dataset):
    """A string of failures must not push the last restorable backup out of the window."""
    good = backup.run()["name"]
    broken = backup.run()["name"]

    manifest_path = backup.backups_root() / broken / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["verified"] = False
    data["errors"] = ["simulated failure"]
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    backup.prune(keep=1)
    remaining = [b["name"] for b in backup.list_all()]
    assert good in remaining, "the only verified backup was deleted"


def test_listing_flags_a_run_that_died_before_writing_a_manifest(dataset):
    (backup.backups_root() / "9999-01-01_000000").mkdir(parents=True)
    listed = backup.list_all()
    partial = next(b for b in listed if b["name"] == "9999-01-01_000000")
    assert partial["verified"] is False
    assert partial["intact"] is False


def test_delete_only_touches_a_backup_that_exists(dataset):
    manifest = backup.run()
    assert backup.delete("no-such-backup") is False
    assert backup.delete("../../etc") is False
    assert backup.delete(manifest["name"]) is True
    assert backup.list_all() == []


def test_the_summary_states_whether_the_copy_shares_a_disk(dataset):
    """A same-disk copy is still worth having, but calling it a backup without saying so
    overstates what it protects against.
    """
    backup.run()
    s = backup.summary()
    assert s["count"] == 1
    assert s["verified_count"] == 1
    assert s["latest_verified"] is True
    assert isinstance(s["same_disk_as_data"], bool)
    assert s["backup_dir"] == str(backup.backups_root())


# ---- through the API ---------------------------------------------------------------


def test_an_admin_can_run_a_backup_and_it_verifies(admin, dataset, oracle):
    from conftest import wait_for_job

    r = admin.post("/api/admin/backups", json={"include_originals": False})
    assert r.status_code == 200, r.text
    job = wait_for_job(admin, r.json()["id"])
    assert job["status"] == "done", job

    listed = admin.get("/api/admin/backups").json()
    assert len(listed) == 1
    assert listed[0]["verified"] is True
    assert listed[0]["intact"] is True

    item = next(i for i in listed[0]["items"] if i.get("dataset_id") == dataset)
    assert item["tables"]["raw_data"] == len(oracle)


def test_the_summary_endpoint_reports_the_latest_backup(admin, dataset):
    from conftest import wait_for_job

    before = admin.get("/api/admin/backups/summary").json()
    assert before["count"] == 0
    assert before["latest_verified"] is False

    wait_for_job(admin, admin.post("/api/admin/backups", json={}).json()["id"])

    after = admin.get("/api/admin/backups/summary").json()
    assert after["count"] == 1
    assert after["latest_verified"] is True
    assert after["latest_at"]


def test_a_failed_verification_fails_the_job_and_keeps_the_files(admin, dataset, monkeypatch):
    """A backup that cannot be read back must not be reported as done. The files stay:
    they are the evidence of what went wrong, and deleting them destroys it.
    """
    from conftest import wait_for_job
    from app.services import backup as svc

    monkeypatch.setattr(svc, "_verify", lambda path, expected: ["simulated corruption"])

    job = wait_for_job(admin, admin.post("/api/admin/backups", json={}).json()["id"])
    assert job["status"] == "error"
    assert "simulated corruption" in (job["error_message"] or "")

    listed = admin.get("/api/admin/backups").json()
    assert len(listed) == 1, "the failed backup should still be on disk to inspect"
    assert listed[0]["verified"] is False


def test_a_viewer_cannot_see_or_run_backups(viewer):
    assert viewer.get("/api/admin/backups").status_code == 403
    assert viewer.get("/api/admin/backups/summary").status_code == 403
    assert viewer.post("/api/admin/backups", json={}).status_code == 403
    assert viewer.delete("/api/admin/backups/anything").status_code == 403


def test_an_editor_may_not_delete_a_backup(editor, dataset):
    """Same rule as datasets: the irreversible action needs the delete permission."""
    assert editor.delete("/api/admin/backups/anything").status_code == 403
    assert editor.post("/api/admin/backups/prune").status_code == 403


def test_deleting_a_backup_that_does_not_exist_is_a_404(admin):
    assert admin.delete("/api/admin/backups/no-such-backup").status_code == 404


def test_deleting_a_backup_removes_it(admin, dataset):
    from conftest import wait_for_job

    wait_for_job(admin, admin.post("/api/admin/backups", json={}).json()["id"])
    name = admin.get("/api/admin/backups").json()[0]["name"]

    assert admin.delete(f"/api/admin/backups/{name}").status_code == 200
    assert admin.get("/api/admin/backups").json() == []
