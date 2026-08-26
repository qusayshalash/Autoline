"""Pruning the catalog's two append-only tables.

This sweep runs by itself, which none of the other retention features do, so most of
what is asserted here is about restraint rather than removal: it must not touch a job
that has not finished, and it must not touch an export job whose file is still on disk -
that row is what the download endpoint reads to learn the file's format, so deleting it
would turn a working link into a 404 with the file sitting right there.
"""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import admin as admin_db
from app.db import catalog
from app.main import app
from app.services import clocks, housekeeping


@pytest.fixture(autouse=True)
def default_policy():
    """Each test starts from the shipped defaults - the settings table is shared, and a
    test that changes the policy would otherwise decide the next test's outcome."""
    admin_db.set_setting(housekeeping.JOBS_RETENTION_KEY, housekeeping.DEFAULT_JOBS_RETENTION_DAYS)
    admin_db.set_setting(
        housekeeping.CLEANING_RETENTION_KEY, housekeeping.DEFAULT_CLEANING_RETENTION_DAYS
    )
    yield
    admin_db.set_setting(housekeeping.JOBS_RETENTION_KEY, housekeeping.DEFAULT_JOBS_RETENTION_DAYS)
    admin_db.set_setting(
        housekeeping.CLEANING_RETENTION_KEY, housekeeping.DEFAULT_CLEANING_RETENTION_DAYS
    )


def _job(kind: str, status: str, *, days_old: float, dataset_id: str = "d1", result=None) -> str:
    """A job row aged by rewriting created_at, which is the only thing the sweep reads."""
    job_id = catalog.create_job(dataset_id, kind)
    fields = {"status": status}
    if result is not None:
        fields["result_json"] = result
    catalog.update_job(job_id, **fields)
    conn = catalog._connection()
    with catalog._lock:
        conn.execute(
            "UPDATE jobs SET created_at = ? WHERE id = ?",
            [clocks.now() - timedelta(days=days_old), job_id],
        )
    return job_id


def _exists(job_id: str) -> bool:
    return catalog.get_job(job_id) is not None


# ---- what it removes --------------------------------------------------------


def test_a_long_finished_job_is_pruned():
    old = _job("import", "done", days_old=60)
    housekeeping.sweep()
    assert not _exists(old)


def test_a_recent_job_is_left_alone():
    fresh = _job("import", "done", days_old=1)
    housekeeping.sweep()
    assert _exists(fresh)


@pytest.mark.parametrize("status", ["done", "error", "cancelled"])
def test_every_settled_status_is_prunable(status):
    job_id = _job("quality", status, days_old=60)
    housekeeping.sweep()
    assert not _exists(job_id)


# ---- what it refuses to remove ----------------------------------------------


@pytest.mark.parametrize("status", ["pending", "running", "cancelling"])
def test_an_unfinished_job_is_never_pruned_however_old(status):
    """Age is not evidence a job is over. A machine that slept for a month wakes with
    rows that look ancient and are still being polled by whoever started them."""
    job_id = _job("import", status, days_old=9999)
    housekeeping.sweep()
    assert _exists(job_id)


def _place_export_file(dataset_id: str, job_id: str, fmt: str = "csv") -> None:
    """Writes the file where download_export would look for it. The real exports_dir is
    used rather than a patched one - it is derived from the temp DATA_DIR the harness
    already points at, and using it means these tests exercise the same path the
    download endpoint builds instead of one that merely resembles it."""
    out = settings.exports_dir / dataset_id
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{job_id}.{fmt}").write_text("col\n1\n", encoding="utf-8")


def test_an_export_whose_file_still_exists_is_kept():
    """The row is not bookkeeping here - it is what the download endpoint reads to learn
    the file's format. Removing it while the file is there breaks a working link."""
    job_id = _job(
        "export", "done", days_old=60, dataset_id="hk_kept", result=json.dumps({"format": "csv"})
    )
    _place_export_file("hk_kept", job_id)

    result = housekeeping.sweep()
    assert _exists(job_id)
    assert result["jobs_held"] >= 1


def test_an_export_whose_file_is_gone_is_pruned():
    """Once export retention has taken the file, the row points at nothing."""
    job_id = _job(
        "export", "done", days_old=60, dataset_id="hk_gone", result=json.dumps({"format": "csv"})
    )
    housekeeping.sweep()
    assert not _exists(job_id)


def test_the_kept_row_still_serves_its_download(admin, dataset):
    """The rule stated as the behaviour it protects rather than as a row count: an old
    export whose file survived is still downloadable after a sweep."""
    r = admin.post(f"/api/datasets/{dataset}/export", json={"format": "csv"})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    from conftest import wait_for_job

    assert wait_for_job(admin, job_id)["status"] == "done"

    conn = catalog._connection()
    with catalog._lock:
        conn.execute(
            "UPDATE jobs SET created_at = ? WHERE id = ?",
            [clocks.now() - timedelta(days=365), job_id],
        )

    housekeeping.sweep()
    assert admin.get(f"/api/datasets/{dataset}/export/{job_id}/download").status_code == 200


def test_an_unreadable_export_result_keeps_the_row():
    """A result_json that will not parse is not evidence the file is gone, and guessing
    wrong in that direction deletes something reachable."""
    job_id = _job("export", "done", days_old=60, dataset_id="hk_bad", result="{not json")
    housekeeping.sweep()
    assert _exists(job_id)


def test_a_failed_export_is_pruned_without_consulting_the_disk():
    """Only a completed export has a file to protect."""
    job_id = _job("export", "error", days_old=60, dataset_id="hk_failed")
    housekeeping.sweep()
    assert not _exists(job_id)


# ---- cleaning history -------------------------------------------------------


def _cleaning_row(dataset_id: str, days_old: float) -> None:
    catalog.record_cleaning_operation(dataset_id, {"dedupe": True}, 10, 9, 1, 0, [])
    conn = catalog._connection()
    with catalog._lock:
        conn.execute(
            "UPDATE cleaning_operations SET created_at = ? WHERE dataset_id = ?",
            [clocks.now() - timedelta(days=days_old), dataset_id],
        )


def test_cleaning_records_outlive_job_rows():
    """A year against a month, deliberately: one is a note that something ran, the other
    is the record of what was done to somebody's data."""
    _cleaning_row("hk_cleaning_mid", days_old=90)
    housekeeping.sweep()
    assert catalog.list_cleaning_operations("hk_cleaning_mid")


def test_a_cleaning_record_past_its_year_is_pruned():
    _cleaning_row("hk_cleaning_old", days_old=400)
    housekeeping.sweep()
    assert catalog.list_cleaning_operations("hk_cleaning_old") == []


# ---- the policy itself ------------------------------------------------------


def test_zero_turns_a_sweep_off():
    admin_db.set_setting(housekeeping.JOBS_RETENTION_KEY, 0)
    job_id = _job("import", "done", days_old=9999)
    assert housekeeping.sweep()["jobs_removed"] == 0
    assert _exists(job_id)


def test_a_dangerously_short_retention_is_clamped_not_obeyed():
    """A 1 typed into the settings table would have the sweep deleting records of things
    that happened yesterday."""
    admin_db.set_setting(housekeeping.JOBS_RETENTION_KEY, 1)
    assert housekeeping.jobs_retention_days() == housekeeping.MIN_RETENTION_DAYS
    job_id = _job("import", "done", days_old=2)
    housekeeping.sweep()
    assert _exists(job_id)


def test_a_nonsense_setting_falls_back_to_the_default():
    admin_db.set_setting(housekeeping.JOBS_RETENTION_KEY, "whenever")
    assert housekeeping.jobs_retention_days() == housekeeping.DEFAULT_JOBS_RETENTION_DAYS


def test_the_sweep_deletes_nothing_when_nothing_is_old_enough():
    # Removal counts only - `jobs_held` is a count across the whole table, and other
    # tests in this session leave export rows standing by design.
    _job("import", "done", days_old=1)
    result = housekeeping.sweep()
    assert result["jobs_removed"] == 0
    assert result["cleaning_removed"] == 0


def test_it_runs_by_itself_without_being_switched_on():
    """The difference from export retention and the activity log, asserted rather than
    left to a comment: the shipped default is a real policy, not zero."""
    assert housekeeping.DEFAULT_JOBS_RETENTION_DAYS > 0
    assert housekeeping.DEFAULT_CLEANING_RETENTION_DAYS > 0


# ---- HTTP -------------------------------------------------------------------


def _role_with(admin, name: str, permissions: list[str]) -> str:
    r = admin.post("/api/roles", json={"name": name, "description": "", "permissions": permissions})
    assert r.status_code in (200, 201), r.text
    return r.json()["slug"]


def _client_for(admin, username: str, slug: str) -> TestClient:
    pw = f"{username}-pw-1"
    r = admin.post("/api/users", json={"username": username, "password": pw, "role": slug})
    assert r.status_code in (200, 201), r.text
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": username, "password": pw}).status_code == 200
    return c


def test_the_status_reports_the_policy(admin):
    r = admin.get("/api/admin/housekeeping")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jobs_retention_days"] == housekeeping.DEFAULT_JOBS_RETENTION_DAYS
    assert body["cleaning_retention_days"] == housekeeping.DEFAULT_CLEANING_RETENTION_DAYS
    assert body["jobs_total"] >= 0


def test_changing_the_policy_takes_effect(admin):
    r = admin.patch("/api/admin/housekeeping", json={"jobs_retention_days": 90})
    assert r.status_code == 200, r.text
    assert r.json()["jobs_retention_days"] == 90
    assert housekeeping.jobs_retention_days() == 90


def test_the_api_clamps_a_short_retention_too(admin):
    r = admin.patch("/api/admin/housekeeping", json={"jobs_retention_days": 2})
    assert r.status_code == 200, r.text
    assert r.json()["jobs_retention_days"] == housekeeping.MIN_RETENTION_DAYS


def test_sweeping_on_demand_removes_what_is_due(admin):
    job_id = _job("import", "done", days_old=60)
    r = admin.post("/api/admin/housekeeping/sweep")
    assert r.status_code == 200, r.text
    assert r.json()["jobs_removed"] >= 1
    assert not _exists(job_id)


def test_watching_is_not_changing(admin):
    """system.view reads the policy; changing it and running it need system.manage."""
    slug = _role_with(admin, "HK Watcher", ["system.view"])
    watcher = _client_for(admin, "hk_watcher", slug)
    assert watcher.get("/api/admin/housekeeping").status_code == 200
    assert watcher.patch(
        "/api/admin/housekeeping", json={"jobs_retention_days": 90}
    ).status_code == 403
    assert watcher.post("/api/admin/housekeeping/sweep").status_code == 403


def test_a_sweep_is_recorded_in_the_activity_log(admin):
    admin.post("/api/admin/housekeeping/sweep")
    entries = admin.get("/api/admin/activity", params={"page_size": 50}).json()["items"]
    assert any(e["action"] == "housekeeping.swept" for e in entries)
