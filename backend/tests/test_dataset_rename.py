"""Renaming a dataset.

There is no dedicated permission for this - it rides on datasets.clean, the existing
"update" permission for the datasets resource, because a rename is a metadata edit in
the same class as a cleaning run and not worth a permission split of its own.
"""

from fastapi.testclient import TestClient

from app.main import app


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


def test_rename_changes_the_display_name(admin, dataset):
    r = admin.patch(f"/api/datasets/{dataset}", json={"name": "  renamed.csv  "})
    assert r.status_code == 200, r.text
    assert r.json()["original_filename"] == "renamed.csv"  # trimmed

    r = admin.get(f"/api/datasets/{dataset}")
    assert r.json()["original_filename"] == "renamed.csv"

    # put the fixture's name back - `dataset` is session-scoped and other tests read it
    r = admin.patch(f"/api/datasets/{dataset}", json={"name": "synthetic.csv"})
    assert r.status_code == 200, r.text


def test_rename_rejects_a_blank_name(admin, dataset):
    r = admin.patch(f"/api/datasets/{dataset}", json={"name": "   "})
    assert r.status_code in (400, 422), r.text


def test_rename_a_missing_dataset_is_404(admin):
    assert admin.patch("/api/datasets/no-such-dataset", json={"name": "x"}).status_code == 404


def test_rename_needs_datasets_clean(admin, dataset):
    slug = _role_with(admin, "Rename Viewer Only", ["datasets.view"])
    viewer = _client_for(admin, "rename_viewer", slug)
    assert viewer.patch(f"/api/datasets/{dataset}", json={"name": "nope.csv"}).status_code == 403


def test_a_role_that_could_clean_can_rename(admin, dataset):
    slug = _role_with(admin, "Rename Cleaner", ["datasets.view", "datasets.clean"])
    cleaner = _client_for(admin, "rename_cleaner", slug)
    r = cleaner.patch(f"/api/datasets/{dataset}", json={"name": "cleaner-renamed.csv"})
    assert r.status_code == 200, r.text
    admin.patch(f"/api/datasets/{dataset}", json={"name": "synthetic.csv"})
