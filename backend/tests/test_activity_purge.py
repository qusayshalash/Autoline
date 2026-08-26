"""Pruning the audit trail.

The trail exists to say what happened. Anything that can edit it is therefore part of
its threat model rather than a convenience, so the tests here are mostly about what the
endpoint refuses: who may call it, what it will not delete, and that it writes down its
own use.

The `admin` fixture signs in as the bootstrap account, which holds super_admin - the one
role granted this permission. `editor` and `viewer` stand in for everyone else.
"""

from datetime import datetime, timedelta, timezone

import pytest
from app.db import admin as admin_db


def _seed(actor_username: str, when: datetime, n: int = 1) -> None:
    """Writes entries with a chosen timestamp. log_activity always stamps 'now', and a
    purge is about age, so the rows have to be dated directly."""
    conn = admin_db.get_connection()
    with admin_db.db_lock:
        for i in range(n):
            conn.execute(
                "INSERT INTO activity_log (id, occurred_at, actor_id, actor_username,"
                " action, target_type, target_id, target_label, detail)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [f"seed-{when.timestamp()}-{i}", when, "seed", actor_username,
                 "test.seeded", "test", "", "", ""],
            )


def _count() -> int:
    return admin_db.list_activity(limit=1)[1]


@pytest.fixture
def old_and_new(request):
    """Ten entries well past any cutoff, and ten from today.

    Tagged with the test's own name: the database is session-scoped, so rows seeded by
    an earlier test are still there and a count of "recent" would otherwise grow with
    every test that ran before this one.
    """
    tag = request.node.name
    now = datetime.now(timezone.utc)
    _seed(f"ancient-{tag}", now - timedelta(days=400), 10)
    _seed(f"recent-{tag}", now - timedelta(days=1), 10)
    return tag


def test_the_plan_counts_without_deleting(admin, old_and_new):
    before = _count()
    r = admin.get("/api/admin/activity/purge-plan", params={"older_than_days": 90})
    assert r.status_code == 200, r.text
    assert r.json()["removed"] >= 10
    assert _count() == before


def test_only_entries_older_than_the_cutoff_go(admin, old_and_new):
    tag = old_and_new
    r = admin.post("/api/admin/activity/purge", json={"older_than_days": 90})
    assert r.status_code == 200, r.text

    rows, _ = admin_db.list_activity(limit=1000)
    assert not any(row["actor_username"] == f"ancient-{tag}" for row in rows)
    assert sum(1 for row in rows if row["actor_username"] == f"recent-{tag}") == 10


def test_the_purge_writes_itself_into_the_trail(admin, old_and_new):
    """The one entry that must survive a purge is the record that a purge happened. A
    trail that quietly shrinks is worse than one that says who shortened it."""
    r = admin.post("/api/admin/activity/purge", json={"older_than_days": 90})
    assert r.status_code == 200, r.text
    removed = r.json()["removed"]

    rows, _ = admin_db.list_activity(limit=20)
    entry = next(row for row in rows if row["action"] == "activity.purged")
    assert str(removed) in entry["detail"]
    assert "90" in entry["detail"]
    assert entry["actor_username"] == "test_admin"


def test_the_reported_remainder_is_the_real_one(admin, old_and_new):
    r = admin.post("/api/admin/activity/purge", json={"older_than_days": 90})
    assert r.json()["remaining"] == _count()


@pytest.mark.parametrize("who", ["editor", "viewer"])
def test_everyone_below_super_admin_is_refused(request, who, old_and_new):
    client = request.getfixturevalue(who)
    before = _count()
    r = client.post("/api/admin/activity/purge", json={"older_than_days": 90})
    assert r.status_code == 403, r.text
    assert _count() == before


def test_a_signed_out_caller_is_refused(anon, old_and_new):
    before = _count()
    r = anon.post("/api/admin/activity/purge", json={"older_than_days": 90})
    assert r.status_code == 401, r.text
    assert _count() == before


@pytest.mark.parametrize("days", [0, 1, 6, -30, 4000])
def test_a_cutoff_inside_the_last_week_is_refused(admin, days, old_and_new):
    """A slip in the box must not be able to erase this morning. Anything under a week
    is rejected outright rather than clamped, so the caller learns their number was not
    the one used."""
    before = _count()
    r = admin.post("/api/admin/activity/purge", json={"older_than_days": days})
    assert r.status_code == 422, r.text
    assert _count() == before


def test_there_is_no_way_to_delete_a_single_entry(admin):
    """Age is the only filter. If deleting by actor or by action were ever added, the
    line most worth erasing would become the easiest to reach - so their absence is a
    property worth asserting rather than a gap."""
    rows, _ = admin_db.list_activity(limit=1)
    entry_id = rows[0]["id"]
    assert admin.delete(f"/api/admin/activity/{entry_id}").status_code in (404, 405)
    assert admin.request("DELETE", "/api/admin/activity").status_code in (404, 405)


def test_purging_when_nothing_is_old_enough_removes_nothing(admin):
    r = admin.post("/api/admin/activity/purge", json={"older_than_days": 3650})
    assert r.status_code == 200, r.text
    assert r.json()["removed"] == 0


def test_a_plain_admin_role_does_not_hold_the_permission():
    """Seeded as a subtraction, so this is the assertion that keeps it subtracted."""
    assert "activity.purge" in admin_db.ALL_PERMISSION_KEYS
    assert "activity.purge" not in admin_db.ADMIN_PERMISSION_KEYS
    admin_role = next(r for r in admin_db.SYSTEM_ROLES if r["slug"] == "admin")
    assert "activity.purge" not in admin_role["permissions"]
