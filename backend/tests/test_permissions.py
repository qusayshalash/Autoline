"""Who may do what.

Every endpoint is checked from three sides - a viewer, an editor and an administrator -
plus with no session at all. The failure mode being guarded against is a new endpoint
added without a guard: the tests below enumerate the routes rather than trusting that
each one remembered to ask.
"""

import pytest


# ---- no session --------------------------------------------------------------------


@pytest.mark.parametrize("method,path", [
    ("get", "/api/datasets"),
    ("get", "/api/auth/me"),
    ("get", "/api/users"),
    ("post", "/api/datasets/any/data"),
    ("post", "/api/datasets/any/statistics"),
    ("post", "/api/datasets/any/pivot"),
    ("post", "/api/datasets/any/clean"),
    ("post", "/api/datasets/any/export"),
    ("delete", "/api/datasets/any"),
])
def test_without_a_session_everything_is_401(anon, method, path):
    r = getattr(anon, method)(path, **({"json": {}} if method == "post" else {}))
    assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"


def test_health_is_the_only_thing_open(anon):
    assert anon.get("/api/health").status_code == 200


def test_a_forged_cookie_is_not_a_session(anon):
    """A hand-written cookie with an admin-shaped payload. Rejected because the signature
    is checked, not because the payload looks wrong.
    """
    anon.cookies.set("access_token", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4Iiwicm9sZSI6ImFkbWluIn0.x")
    assert anon.get("/api/datasets").status_code == 401
    anon.cookies.clear()


# ---- the matrix --------------------------------------------------------------------


def test_a_viewer_may_read(viewer, dataset):
    assert viewer.get("/api/datasets").status_code == 200
    assert viewer.post(f"/api/datasets/{dataset}/data", json={"source": "raw"}).status_code == 200
    assert viewer.post(
        f"/api/datasets/{dataset}/statistics", json={"group_by": "baalut", "source": "raw"}
    ).status_code == 200
    assert viewer.post(
        f"/api/datasets/{dataset}/pivot",
        json={"row_column": "baalut", "column_column": "sug_delek_nm", "source": "raw"},
    ).status_code == 200


def test_a_viewer_may_not_export(viewer, dataset):
    """Reading on screen and taking a copy away are different permissions, and the viewer
    role holds only datasets.view.
    """
    r = viewer.post(f"/api/datasets/{dataset}/export", json={"format": "csv", "source": "raw"})
    assert r.status_code == 403, r.text


def test_a_viewer_may_not_upload(viewer, csv_path):
    with open(csv_path, "rb") as f:
        r = viewer.post("/api/datasets/upload", files={"file": ("x.csv", f, "text/csv")})
    assert r.status_code == 403, r.text


def test_a_viewer_may_not_clean(viewer, dataset):
    r = viewer.post(f"/api/datasets/{dataset}/clean", json={"dedupe": True})
    assert r.status_code == 403, r.text


def test_a_viewer_may_not_delete(viewer, dataset):
    r = viewer.delete(f"/api/datasets/{dataset}")
    assert r.status_code == 403, r.text


def test_a_viewer_may_not_see_or_manage_users(viewer):
    assert viewer.get("/api/users").status_code == 403
    r = viewer.post(
        "/api/users", json={"username": "sneaky", "password": "password1", "role": "admin"}
    )
    assert r.status_code == 403, r.text


def test_an_editor_may_export_and_clean(editor, dataset):
    assert editor.post(
        f"/api/datasets/{dataset}/export", json={"format": "csv", "source": "raw"}
    ).status_code == 200
    assert editor.post(f"/api/datasets/{dataset}/clean", json={}).status_code == 200


def test_an_editor_may_not_delete_a_dataset(editor, dataset):
    """The one thing that cannot be undone is the one thing an editor may not do."""
    r = editor.delete(f"/api/datasets/{dataset}")
    assert r.status_code == 403, r.text


def test_an_editor_may_not_manage_users(editor):
    assert editor.get("/api/users").status_code == 403
    r = editor.post(
        "/api/users", json={"username": "sneaky2", "password": "password1", "role": "editor"}
    )
    assert r.status_code == 403, r.text


def test_an_editor_may_not_escalate_their_own_role(editor, admin):
    """The interesting attempt: not creating an admin, but promoting yourself."""
    me = editor.get("/api/auth/me").json()
    r = editor.patch(f"/api/users/{me['id']}", json={"role": "super_admin"})
    assert r.status_code == 403, r.text
    assert editor.get("/api/auth/me").json()["role"] == "editor"


def test_an_admin_may_do_all_of_it(admin, dataset):
    assert admin.get("/api/users").status_code == 200
    assert admin.post(
        f"/api/datasets/{dataset}/export", json={"format": "csv", "source": "raw"}
    ).status_code == 200
    assert admin.post(f"/api/datasets/{dataset}/clean", json={}).status_code == 200


# ---- session lifecycle -------------------------------------------------------------


def test_a_wrong_password_does_not_open_a_session(api):
    r = api.post("/api/auth/login", json={"username": "test_admin", "password": "wrong"})
    assert r.status_code == 401, r.text


def test_an_unknown_username_is_rejected_the_same_way(api):
    """Same status and no hint about whether the account exists."""
    r = api.post("/api/auth/login", json={"username": "nobody", "password": "wrong"})
    assert r.status_code == 401, r.text


def test_logging_out_ends_the_session(admin, api):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    assert client.post(
        "/api/auth/login", json={"username": "test_admin", "password": "test-admin-pw"}
    ).status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_disabling_an_account_ends_its_live_session_immediately(admin):
    """The reason the current user is re-read from the database on every request instead
    of being trusted from the token: without it, a disabled account keeps working until
    its token expires - up to twelve hours of access after being revoked.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    r = admin.post(
        "/api/users",
        json={"username": "test_suspend", "password": "test-suspend-pw", "role": "viewer"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["id"]

    victim = TestClient(app)
    assert victim.post(
        "/api/auth/login", json={"username": "test_suspend", "password": "test-suspend-pw"}
    ).status_code == 200
    assert victim.get("/api/datasets").status_code == 200

    assert admin.patch(f"/api/users/{user_id}", json={"status": "inactive"}).status_code == 200

    # same cookie, still unexpired, now worthless
    assert victim.get("/api/datasets").status_code == 401


def test_a_permission_change_takes_effect_without_re_login(admin):
    """Permissions are resolved per request from the role, so granting one applies at
    once - the same mechanism, seen from the other direction.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    r = admin.post(
        "/api/users",
        json={"username": "test_promote", "password": "test-promote-pw", "role": "viewer"},
    )
    user_id = r.json()["id"]

    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "test_promote", "password": "test-promote-pw"})
    assert client.get("/api/users").status_code == 403

    assert admin.patch(f"/api/users/{user_id}", json={"role": "admin"}).status_code == 200
    assert client.get("/api/users").status_code == 200

    # ...and revoked just as immediately. Restoring the role also leaves the bootstrap
    # account as the only administrator, which the last-administrator test needs.
    assert admin.patch(f"/api/users/{user_id}", json={"role": "viewer"}).status_code == 200
    assert client.get("/api/users").status_code == 403


def test_the_last_administrator_cannot_lock_everyone_out(admin):
    """Deleting or demoting the only remaining admin would leave a system nobody can
    administer, with no way back in short of editing the database by hand.
    """
    me = admin.get("/api/auth/me").json()
    admins = [
        u for u in admin.get("/api/users").json()
        if u["role"] in ("admin", "super_admin") and u["status"] == "active"
    ]
    if len(admins) > 1:
        pytest.skip("another administrator exists, so this guard is not the one under test")

    # 409, not 400: the request is well formed, it conflicts with the state of the system
    assert admin.delete(f"/api/users/{me['id']}").status_code == 409
    assert admin.patch(f"/api/users/{me['id']}", json={"status": "inactive"}).status_code == 409
    assert admin.get("/api/auth/me").status_code == 200
