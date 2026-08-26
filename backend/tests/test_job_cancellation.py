"""Cancelling a job.

Nothing here kills a thread mid-statement - DuckDB does not offer that, and the module
docstring in app/jobs.py says why cancellation is cooperative instead: it only takes
effect at a checkpoint, and the one checkpoint every runner has for certain is its very
first line, before it has touched anything. That is what these tests exploit to stay
deterministic: mark a job "cancelling" before it starts, then call the runner function
directly in the test thread instead of through the real executor, so there is no race
to win - check_cancelled() raises on the first line and the runner records "cancelled"
without ever reaching the work it would otherwise do.

The HTTP-level tests cover the part that is actually about authorization: cancelling a
job answers to the same permission its kind would have needed to start it.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import catalog
from app.jobs import JobCancelled, check_cancelled
from app.main import app
from app.models.schemas import ExportRequest
from app.routers import admin as admin_router
from app.services import export as export_service
from app.services import ingestion, quality


def _cancelling_job(dataset_id: str = "", kind: str = "import") -> str:
    job_id = catalog.create_job(dataset_id, kind)
    assert catalog.request_job_cancel(job_id) == "cancelling"
    assert catalog.is_cancelling(job_id)
    return job_id


def test_check_cancelled_is_a_noop_for_an_ordinary_job():
    job_id = catalog.create_job("", "import")
    check_cancelled(job_id)  # must not raise


def test_check_cancelled_raises_once_cancelling():
    job_id = _cancelling_job()
    with pytest.raises(JobCancelled):
        check_cancelled(job_id)


def test_request_job_cancel_on_a_missing_job_returns_none():
    assert catalog.request_job_cancel("no-such-job") is None


def test_request_job_cancel_leaves_a_finished_job_alone():
    job_id = catalog.create_job("", "import")
    catalog.update_job(job_id, status="done")
    assert catalog.request_job_cancel(job_id) == "done"
    row = catalog.get_job(job_id)
    assert row["status"] == "done"  # not overwritten to "cancelling"


def test_import_stops_at_its_first_checkpoint():
    """Raises before find_raw_path() runs - otherwise a dataset id that doesn't exist
    would fail with a FileNotFoundError, landing on "error" instead of "cancelled"."""
    job_id = _cancelling_job(kind="import")
    ingestion.run_import_job("no-such-dataset", job_id, "utf-8", ",", True)
    assert catalog.get_job(job_id)["status"] == "cancelled"


def test_quality_stops_at_its_first_checkpoint():
    job_id = _cancelling_job(kind="quality")
    quality.run_quality_job("no-such-dataset", job_id)
    assert catalog.get_job(job_id)["status"] == "cancelled"


def test_export_stops_at_its_first_checkpoint():
    job_id = _cancelling_job(kind="export")
    export_service.run_export_job("no-such-dataset", job_id, ExportRequest(format="csv"))
    assert catalog.get_job(job_id)["status"] == "cancelled"


def test_backup_stops_at_its_first_checkpoint():
    """Raises before backup_service.run() is ever called, so no backup directory is
    created for a job that never did anything."""
    from app.config import settings

    before = set(settings.backups_dir.glob("*")) if settings.backups_dir.exists() else set()
    job_id = _cancelling_job(kind="backup")
    admin_router._run_backup_job(job_id, False)
    assert catalog.get_job(job_id)["status"] == "cancelled"
    after = set(settings.backups_dir.glob("*")) if settings.backups_dir.exists() else set()
    assert after == before


def test_compaction_stops_at_its_first_checkpoint():
    job_id = _cancelling_job(kind="compact")
    admin_router._run_compaction_job("no-such-dataset", job_id)
    assert catalog.get_job(job_id)["status"] == "cancelled"


# ---- HTTP: cancelling answers to the same permission starting the job would have ----


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


def test_cancel_a_missing_job_is_404(admin):
    assert admin.post("/api/jobs/no-such-job/cancel").status_code == 404


def test_cancel_needs_the_permission_the_job_kind_would_have_needed(admin):
    """A role holding only datasets.view (the quality-job permission) may cancel a
    quality job but not a backup, which needs system.manage."""
    quality_job = catalog.create_job("d1", "quality")
    backup_job = catalog.create_job("", "backup")

    slug = _role_with(admin, "Cancel Viewer Only", ["datasets.view"])
    viewer = _client_for(admin, "cancel_viewer", slug)

    r = viewer.post(f"/api/jobs/{quality_job}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelling"

    r = viewer.post(f"/api/jobs/{backup_job}/cancel")
    assert r.status_code == 403, r.text


def test_cancelling_an_already_finished_job_is_a_no_op(admin):
    job_id = catalog.create_job("", "import")
    catalog.update_job(job_id, status="done")
    r = admin.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
