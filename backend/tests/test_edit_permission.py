"""Who ends up able to correct a record, on a fresh install and on an upgraded one.

`datasets.edit` is new, and the seeder only hands new permissions to super_admin - a
built-in role that already exists is never touched again, deliberately, so that an
administrator's own edits to it survive a restart. Without a backfill the Admin role on
every installation already running would get nothing, and the feature would be invisible
to exactly the people it was built for.

The backfill grants it to whoever can already delete a dataset. Deleting destroys every
row in it; correcting changes one. Whoever was trusted with the first is trusted with the
second, and nobody else gains anything.
"""

from app.db import admin as admin_db


def _role_with(admin, name: str, permissions: list[str]) -> str:
    r = admin.post(
        "/api/roles", json={"name": name, "description": "", "permissions": permissions}
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["slug"]


def test_the_permission_is_in_the_catalogue():
    assert "datasets.edit" in admin_db.ALL_PERMISSION_KEYS


def test_it_does_not_collide_with_another_action_in_the_same_module():
    """The permission grid is a module x action matrix keyed by "module:action", so two
    entries sharing a pair make one of the two checkboxes unreachable. datasets.clean
    already holds datasets:update."""
    pairs = [(module, action) for _, module, action in admin_db.PERMISSIONS]
    assert len(pairs) == len(set(pairs)), "two permissions share a module and action"


def test_the_administrator_roles_have_it(admin):
    for slug in ("super_admin", "admin"):
        role = admin.get(f"/api/roles/{slug}").json()
        assert "datasets.edit" in role["permissions"], slug


def test_the_editor_role_does_not(admin):
    """"Admin only" was the decision. An editor uploads, cleans and exports; overwriting
    what the source file says is not part of that."""
    role = admin.get("/api/roles/editor").json()
    assert "datasets.edit" not in role["permissions"]
    assert "datasets.clean" in role["permissions"], "and nothing was taken away"


def test_the_viewer_role_does_not(admin):
    assert admin.get("/api/roles/viewer").json()["permissions"] == ["datasets.view"]


def test_the_backfill_reaches_a_custom_role_that_can_delete(admin):
    slug = _role_with(admin, "Data Steward", ["datasets.view", "datasets.delete"])
    admin_db.seed()  # the backfill runs on every startup
    role = admin.get(f"/api/roles/{slug}").json()
    assert "datasets.edit" in role["permissions"]


def test_the_backfill_grants_nothing_to_a_role_that_cannot_delete(admin):
    slug = _role_with(admin, "Data Reader", ["datasets.view", "datasets.export"])
    admin_db.seed()
    role = admin.get(f"/api/roles/{slug}").json()
    assert "datasets.edit" not in role["permissions"]
    assert sorted(role["permissions"]) == ["datasets.export", "datasets.view"]


def test_running_the_backfill_again_changes_nothing(admin):
    """It runs on every startup; the second run must be a no-op rather than a duplicate
    grant or an error."""
    before = sorted(admin.get("/api/roles/admin").json()["permissions"])
    admin_db.seed()
    admin_db.seed()
    assert sorted(admin.get("/api/roles/admin").json()["permissions"]) == before
