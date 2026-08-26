"""Who may read a dataset.

Being signed in is not the question. Until this was fixed, the data routes asked only
that - `Depends(get_current_user)` proves who is asking and never asks whether they may -
while the statistics endpoint beside them required `datasets.view`. The aggregate was
guarded and the rows underneath it were not, which is the wrong way round: nobody who
wants the data needs the summary.

The account used here holds a role with no permissions at all. Every assertion is that it
gets nothing.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

NOBODY_USER = "authz_nobody"
NOBODY_PW = "authz-nobody-pw-1"


@pytest.fixture(scope="module")
def nobody(admin) -> TestClient:
    """Signed in, and holding a role that grants nothing."""
    r = admin.post(
        "/api/roles",
        json={"name": "Authz Nothing", "description": "holds no permissions", "permissions": []},
    )
    assert r.status_code in (200, 201), r.text
    slug = r.json()["slug"]

    r = admin.post(
        "/api/users",
        json={"username": NOBODY_USER, "password": NOBODY_PW, "role": slug},
    )
    assert r.status_code in (200, 201), r.text

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": NOBODY_USER, "password": NOBODY_PW})
    assert login.status_code == 200, login.text
    return client


def test_the_account_really_is_signed_in(nobody):
    """Otherwise every assertion below would pass for the wrong reason - a 403 proves
    nothing if the caller was simply never authenticated."""
    r = nobody.get("/api/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["username"] == NOBODY_USER
    assert r.json()["permissions"] == []


def test_the_rows_are_refused(nobody, dataset):
    r = nobody.post(f"/api/datasets/{dataset}/data", json={"page": 1, "page_size": 5})
    assert r.status_code == 403, r.text


@pytest.mark.parametrize(
    "path",
    ["columns", "stats", "profile", "data/distinct-values?column=baalut"],
)
def test_every_other_read_route_is_refused(nobody, dataset, path):
    assert nobody.get(f"/api/datasets/{dataset}/{path}").status_code == 403


def test_grouping_is_refused(nobody, dataset):
    r = nobody.post(f"/api/datasets/{dataset}/group", json={"columns": ["baalut"]})
    assert r.status_code == 403, r.text


def test_the_listing_is_refused(nobody):
    """The listing is dataset contents too: file names, row counts, sizes and every
    column name."""
    assert nobody.get("/api/datasets").status_code == 403


def test_the_detail_and_quality_report_are_refused(nobody, dataset):
    assert nobody.get(f"/api/datasets/{dataset}").status_code == 403
    assert nobody.get(f"/api/datasets/{dataset}/quality").status_code == 403


def test_the_cleaning_history_is_refused(nobody, dataset):
    assert nobody.get(f"/api/datasets/{dataset}/cleaning-operations").status_code == 403


def test_the_statistics_stay_refused(nobody, dataset):
    """This one was already guarded. Asserted so a later refactor cannot loosen it while
    tightening the others."""
    r = nobody.post(f"/api/datasets/{dataset}/statistics", json={"group_by": "baalut"})
    assert r.status_code == 403, r.text


def test_export_needs_more_than_the_export_permission(admin, dataset):
    """Export hands over the same rows as a file. A role holding `datasets.export` alone
    would otherwise download in bulk exactly what it is forbidden to read on screen, which
    would make every guard above decorative."""
    r = admin.post(
        "/api/roles",
        json={"name": "Authz Export Only", "description": "", "permissions": ["datasets.export"]},
    )
    assert r.status_code in (200, 201), r.text
    slug = r.json()["slug"]
    assert admin.post(
        "/api/users",
        json={"username": "authz_exporter", "password": "authz-exporter-pw-1", "role": slug},
    ).status_code in (200, 201)

    client = TestClient(app)
    assert client.post(
        "/api/auth/login",
        json={"username": "authz_exporter", "password": "authz-exporter-pw-1"},
    ).status_code == 200

    r = client.post(f"/api/datasets/{dataset}/export", json={"format": "csv"})
    assert r.status_code == 403, r.text


def test_a_viewer_still_reads_everything_it_used_to(viewer, dataset):
    """The other half of the change: tightening these routes must not take anything away
    from the roles that were always meant to reach them. Viewer holds `datasets.view` and
    nothing else."""
    assert viewer.get("/api/datasets").status_code == 200
    assert viewer.get(f"/api/datasets/{dataset}").status_code == 200
    assert viewer.get(f"/api/datasets/{dataset}/columns").status_code == 200
    assert viewer.get(f"/api/datasets/{dataset}/stats").status_code == 200
    assert viewer.post(
        f"/api/datasets/{dataset}/data", json={"page": 1, "page_size": 5}
    ).status_code == 200
