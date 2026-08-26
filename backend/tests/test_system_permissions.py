"""Seeing the system versus changing it.

system.view used to gate both, so there was no way to let somebody watch disk usage and
backup history without also handing them the retention policy - which deletes files - and
the backup schedule. The reads and the writes are now separate permissions.

A split is not a new capability, so the test that matters most here is the one asserting
nobody lost anything: every role that could take a backup yesterday can still take one.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import admin as admin_db
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


@pytest.fixture(scope="module")
def watcher(admin) -> TestClient:
    """The role the split exists for: reads the system, changes nothing."""
    slug = _role_with(admin, "Sys Watcher", ["system.view"])
    return _client_for(admin, "sys_watcher", slug)


READS = ["/api/admin/system", "/api/admin/storage", "/api/admin/backups", "/api/admin/overview"]


@pytest.mark.parametrize("path", READS)
def test_the_watcher_can_look(watcher, path):
    assert watcher.get(path).status_code == 200


def test_the_watcher_cannot_change_the_retention_policy(watcher):
    """The one that made the old arrangement wrong: retention decides what gets deleted."""
    r = watcher.patch("/api/admin/storage/retention", json={"hours": 24})
    assert r.status_code == 403, r.text


def test_the_watcher_cannot_start_a_backup(watcher):
    assert watcher.post("/api/admin/backups", json={}).status_code == 403


def test_the_watcher_cannot_change_the_backup_schedule(watcher):
    r = watcher.patch("/api/admin/backups/schedule", json={"every_hours": 24})
    assert r.status_code == 403, r.text


def test_the_watcher_cannot_clean_storage(watcher):
    r = watcher.post(
        "/api/admin/storage/cleanup",
        json={"expired_exports": True, "all_exports": False, "intermediates": True},
    )
    assert r.status_code == 403, r.text


def test_the_watcher_cannot_prune_backups(watcher):
    assert watcher.post("/api/admin/backups/prune").status_code == 403


def test_deleting_datasets_no_longer_reaches_the_backups(admin):
    """Backups are the way back from a deleted dataset. Whoever can delete the data should
    not, by the same permission, be able to destroy what would undo it."""
    slug = _role_with(admin, "Sys Data Deleter", ["datasets.view", "datasets.delete"])
    c = _client_for(admin, "sys_deleter", slug)
    assert c.post("/api/admin/backups/prune").status_code == 403
    assert c.delete("/api/admin/backups/anything.duckdb").status_code == 403


def test_an_upgraded_install_keeps_what_it_had(admin):
    """The migration, not the seeder. system.manage is new, and only super_admin picks up
    new permissions - so without the backfill an existing Admin role would have lost
    backups and retention on the next restart."""
    role = admin.get("/api/roles/admin").json()
    assert "system.view" in role["permissions"]
    assert "system.manage" in role["permissions"]


def test_the_backfill_reaches_custom_roles_too(admin):
    """A role somebody built themselves out of system.view could do these things before
    the split, so it must still be able to."""
    slug = _role_with(admin, "Sys Legacy", ["system.view"])
    admin_db.seed()  # the backfill runs on every startup
    role = admin.get(f"/api/roles/{slug}").json()
    assert "system.manage" in role["permissions"]


def test_the_backfill_grants_nothing_to_a_role_without_the_old_permission(admin):
    slug = _role_with(admin, "Sys Unrelated", ["datasets.view"])
    admin_db.seed()
    role = admin.get(f"/api/roles/{slug}").json()
    assert "system.manage" not in role["permissions"]
    assert role["permissions"] == ["datasets.view"]


def test_an_admin_can_still_do_all_of_it(admin):
    """The other half: the split must not have cost the built-in administrator anything."""
    assert admin.patch("/api/admin/storage/retention", json={"hours": 0}).status_code == 200
    assert admin.post("/api/admin/backups/prune").status_code == 200
