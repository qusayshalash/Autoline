"""Saved views.

A view is private until shared. These check who sees what, and that a view does not
reach past the file or the person it belongs to.
"""

import pytest

STATE = {
    "source": "cleaned",
    "search": "toyota",
    "search_columns": [],
    "filters": [{"column": "year", "op": "gte", "value": "2020"}],
    "sort_by": "year",
    "sort_dir": "desc",
    "group_by": [],
    "only_recent": False,
    "only_removed": False,
}


@pytest.fixture(autouse=True)
def _clean_slate(admin, viewer, editor, dataset):
    """Each test starts with no views on the shared dataset."""
    for client in (admin, viewer, editor):
        for v in client.get(f"/api/datasets/{dataset}/views").json():
            if v["mine"]:
                client.delete(f"/api/datasets/{dataset}/views/{v['id']}")
    yield


# ---- saved views ----


def test_signed_out_nothing(anon, dataset):
    assert anon.get(f"/api/datasets/{dataset}/views").status_code == 401


def test_views_for_a_missing_dataset_are_404(viewer):
    assert viewer.get("/api/datasets/nope/views").status_code == 404


def _without_blanks(state: dict) -> dict:
    """A filter rule comes back with its unused fields as null; the same rule."""
    return {
        **state,
        "filters": [{k: v for k, v in f.items() if v is not None} for f in state["filters"]],
    }


def _save(client, dataset, name="Toyota since 2020", shared=False):
    r = client.post(
        f"/api/datasets/{dataset}/views", json={"name": name, "state": STATE, "shared": shared}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_a_view_is_saved_and_listed(viewer, dataset):
    view = _save(viewer, dataset)
    assert view["mine"] and view["can_delete"] and not view["shared"]
    assert _without_blanks(view["state"]) == STATE
    listed = viewer.get(f"/api/datasets/{dataset}/views").json()
    assert [v["id"] for v in listed] == [view["id"]]


def test_a_private_view_is_invisible_to_others(viewer, editor, dataset):
    view = _save(viewer, dataset)
    assert editor.get(f"/api/datasets/{dataset}/views").json() == []
    # by link too, and as missing rather than forbidden: whether it exists is theirs
    r = editor.get(f"/api/datasets/{dataset}/views/{view['id']}")
    assert r.status_code == 404
    assert r.json()["code"] == "view_not_found"


def test_a_shared_view_is_seen_and_opened_by_others(viewer, editor, dataset):
    view = _save(viewer, dataset, shared=True)
    listed = editor.get(f"/api/datasets/{dataset}/views").json()
    assert [v["id"] for v in listed] == [view["id"]]
    assert listed[0]["mine"] is False
    assert listed[0]["owner_username"] == "test_viewer"
    assert editor.get(f"/api/datasets/{dataset}/views/{view['id']}").status_code == 200


def test_only_the_owner_changes_a_shared_view(viewer, editor, admin, dataset):
    view = _save(viewer, dataset, shared=True)
    for client in (editor, admin):
        r = client.patch(f"/api/datasets/{dataset}/views/{view['id']}", json={"name": "mine now"})
        assert r.status_code == 403
        assert r.json()["code"] == "view_not_yours"


def test_an_editor_cannot_delete_someone_elses_shared_view(viewer, editor, dataset):
    view = _save(viewer, dataset, shared=True)
    assert editor.delete(f"/api/datasets/{dataset}/views/{view['id']}").status_code == 403


def test_an_administrator_can_delete_a_shared_view(viewer, admin, dataset):
    view = _save(viewer, dataset, shared=True)
    listed = admin.get(f"/api/datasets/{dataset}/views").json()
    assert listed[0]["can_delete"] is True
    assert admin.delete(f"/api/datasets/{dataset}/views/{view['id']}").status_code == 200
    assert viewer.get(f"/api/datasets/{dataset}/views").json() == []


def test_the_owner_updates_renames_and_stops_sharing(viewer, editor, dataset):
    view = _save(viewer, dataset, shared=True)
    newer = {**STATE, "search": "kia"}
    r = viewer.patch(
        f"/api/datasets/{dataset}/views/{view['id']}",
        json={"name": "Kia", "state": newer, "shared": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Kia" and r.json()["state"]["search"] == "kia"
    assert editor.get(f"/api/datasets/{dataset}/views").json() == []


def test_a_blank_name_is_refused(viewer, dataset):
    r = viewer.post(
        f"/api/datasets/{dataset}/views", json={"name": "   ", "state": STATE, "shared": False}
    )
    assert r.status_code == 400
    assert r.json()["code"] == "view_name_blank"


def test_a_view_with_a_misspelled_filter_is_refused(viewer, dataset):
    state = {**STATE, "filters": [{"column": "year", "opp": "gte", "value": "2020"}]}
    r = viewer.post(
        f"/api/datasets/{dataset}/views", json={"name": "x", "state": state, "shared": False}
    )
    assert r.status_code == 422


def test_a_view_belongs_to_its_dataset(viewer, dataset):
    view = _save(viewer, dataset)
    other = "0" * 32
    assert viewer.get(f"/api/datasets/{other}/views/{view['id']}").status_code == 404


def test_sharing_is_logged_and_private_saves_are_not(viewer, admin, dataset):
    _save(viewer, dataset, name="quiet")
    _save(viewer, dataset, name="loud", shared=True)
    entries = admin.get("/api/admin/activity").json()["items"][:20]
    details = [e.get("detail") or "" for e in entries if e["action"] == "view.shared"]
    assert "view: loud" in details
    assert not any("quiet" in d for d in (e.get("detail") or "" for e in entries))


def test_there_is_a_limit_per_person(viewer, dataset, monkeypatch):
    from app.routers import views

    monkeypatch.setattr(views, "MAX_VIEWS_PER_PERSON", 2)
    _save(viewer, dataset, name="one")
    _save(viewer, dataset, name="two")
    r = viewer.post(
        f"/api/datasets/{dataset}/views", json={"name": "three", "state": STATE, "shared": False}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "too_many_views"


def test_deleting_a_user_keeps_what_they_shared(admin, dataset):
    r = admin.post(
        "/api/users",
        json={"username": "test_leaver", "password": "test-leaver-pw", "role": "viewer"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["id"]
    from fastapi.testclient import TestClient

    from app.main import app

    leaver = TestClient(app)
    leaver.post("/api/auth/login", json={"username": "test_leaver", "password": "test-leaver-pw"})
    _save(leaver, dataset, name="private one")
    kept = _save(leaver, dataset, name="shared one", shared=True)

    assert admin.delete(f"/api/users/{user_id}").status_code == 200

    names = [v["name"] for v in admin.get(f"/api/datasets/{dataset}/views").json()]
    assert names == ["shared one"]
    # and an administrator can still tidy it away
    assert admin.delete(f"/api/datasets/{dataset}/views/{kept['id']}").status_code == 200
