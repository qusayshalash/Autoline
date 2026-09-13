"""Reading a job answers to the same permission as starting one.

A job id is an opaque UUID, which is why reading was left on authentication alone at
first. That is not a guard - it only means the id has to be handed over rather than
guessed, and a finished export job carries the dataset id, the export's filename and
its size. An account holding no permissions at all could read any job whose id it had.
"""

import pytest
from conftest import wait_for_job
from fastapi.testclient import TestClient

from app.main import app
from app.routers.jobs import _JOB_PERMISSIONS


@pytest.fixture(scope="module")
def nobody(admin) -> TestClient:
    """An account with a real session and not one single permission - the shape that
    proves a check exists rather than merely that some other check happened to fire."""
    admin.post("/api/roles", json={"name": "Test Empty", "description": "", "permissions": []})
    r = admin.post(
        "/api/users",
        json={"username": "test_nobody", "password": "test-nobody-pw", "role": "test_empty"},
    )
    assert r.status_code in (200, 409), r.text

    client = TestClient(app)
    r = client.post(
        "/api/auth/login", json={"username": "test_nobody", "password": "test-nobody-pw"}
    )
    assert r.status_code == 200, r.text
    return client


@pytest.fixture(scope="module")
def export_job(admin, dataset) -> str:
    r = admin.post(f"/api/datasets/{dataset}/export", json={"format": "csv"})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    assert wait_for_job(admin, job_id)["status"] == "done"
    return job_id


# ---- reading ---------------------------------------------------------------------------

def test_an_account_with_no_permissions_cannot_read_a_job(nobody, export_job):
    r = nobody.get(f"/api/jobs/{export_job}")
    assert r.status_code == 403, r.text
    assert export_job not in r.text, "the refusal echoed the job id back"


def test_the_refusal_does_not_leak_the_result(nobody, export_job):
    """The payload that made this worth fixing: filename, size and dataset id."""
    body = nobody.get(f"/api/jobs/{export_job}").text
    for leaked in ("filename", "size_bytes", "dataset_id", ".csv"):
        assert leaked not in body, leaked


def test_a_viewer_cannot_read_an_export_job(viewer, export_job):
    """A viewer may look at data but not export it, so someone else's export is not
    theirs to watch either."""
    assert viewer.get(f"/api/jobs/{export_job}").status_code == 403


def test_an_editor_can_read_an_export_job(editor, export_job):
    """An editor holds both datasets.view and datasets.export, so this must still work -
    a guard that refuses the people who need it is the other way to get this wrong."""
    r = editor.get(f"/api/jobs/{export_job}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == export_job


def test_an_administrator_can_read_a_job(admin, export_job):
    assert admin.get(f"/api/jobs/{export_job}").status_code == 200


def test_an_unknown_job_is_404_for_everyone(nobody, admin):
    ghost = "0" * 32
    assert admin.get(f"/api/jobs/{ghost}").status_code == 404
    assert nobody.get(f"/api/jobs/{ghost}").status_code == 404


def test_reading_a_job_still_needs_a_session(anon, export_job):
    assert anon.get(f"/api/jobs/{export_job}").status_code == 401


# ---- the import job an editor owns ---------------------------------------------------------

def test_a_viewer_cannot_read_an_import_job(admin, viewer):
    """Import answers to datasets.upload, which a viewer does not have."""
    up = admin.post(
        "/api/datasets/upload",
        files={"file": ("test_jobauth.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert up.status_code == 200, up.text
    did = up.json()["dataset_id"]
    started = admin.post(
        f"/api/datasets/{did}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert started.status_code == 200, started.text
    job_id = started.json()["id"]
    wait_for_job(admin, job_id)

    assert viewer.get(f"/api/jobs/{job_id}").status_code == 403
    assert admin.get(f"/api/jobs/{job_id}").status_code == 200


# ---- cancelling keeps the behaviour it had ---------------------------------------------------

def test_cancelling_is_refused_for_the_same_accounts(nobody, viewer, export_job):
    assert nobody.post(f"/api/jobs/{export_job}/cancel").status_code == 403
    assert viewer.post(f"/api/jobs/{export_job}/cancel").status_code == 403


def test_cancelling_a_finished_job_is_still_a_no_op_for_someone_allowed(editor, export_job):
    r = editor.post(f"/api/jobs/{export_job}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done", "a finished job must not be moved to cancelling"


# ---- the map itself ----------------------------------------------------------------------------

def test_every_kind_of_job_the_system_creates_is_listed():
    """An unlisted kind is refused, so a new one must be added here deliberately. This
    test is what turns that from a silent 403 into a failing build."""
    import ast
    from pathlib import Path

    created: set[str] = set()
    app_dir = Path(__file__).resolve().parent.parent / "app"
    for path in app_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", getattr(node.func, "id", "")) == "create_job"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
            ):
                created.add(node.args[1].value)

    assert created, "the scan found no create_job calls - it has stopped working"
    missing = sorted(created - set(_JOB_PERMISSIONS))
    assert not missing, f"job kinds with no permission rule: {', '.join(missing)}"


def test_an_unknown_kind_is_refused_rather_than_allowed(admin, export_job):
    """The default matters more than the entries: getting here with a kind nobody listed
    must not mean 'anyone may read it'."""
    from app.routers import jobs as jobs_router

    row = {"kind": "some_kind_added_later"}
    user = {"permissions": list(_JOB_PERMISSIONS["backup"]) + ["datasets.view"]}
    with pytest.raises(Exception) as excinfo:
        jobs_router._require_job_access(row, user)
    assert "403" in str(excinfo.value) or "permission" in str(excinfo.value).lower()
