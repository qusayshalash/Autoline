"""Synchronising a dataset with the government registry.

The network is never touched: each test hands `preview` a snapshot file written the way
the government API writes it - an `_id` column first, and the three code columns without
their leading zeros. What is checked is the comparison and what applying it does.
"""

from pathlib import Path

import pytest
from conftest import wait_for_job

from app.services import registry_sync

HEADER = "mispar_rechev,tozeret_cd,degem_cd,tozeret_nm,tokef_dt"


def _upload(admin, tmp_path_factory, lines: list[str]) -> str:
    path = tmp_path_factory.mktemp("registry") / "registry.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("registry.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    assert admin.put(
        f"/api/datasets/{dataset_id}/key", json={"columns": ["mispar_rechev"]}
    ).status_code == 200
    return dataset_id


# what the dataset starts with: padded, as the downloaded file has it
LOCAL = [
    "01000037,0404,0060,לקסוס יפן,2027-02-28",
    "01000039,0152,0054,מרצדס בנץ,2026-05-01",
    "01000068,0413,0005,קיה קוריאה,2026-01-01",
    "01000099,0413,0005,קיה קוריאה,2026-03-03",
]


def snapshot(tmp_path: Path, rows: list[str]) -> Path:
    path = tmp_path / "snapshot.csv"
    body = [f"_id,{HEADER}"] + [f"{i + 1},{r}" for i, r in enumerate(rows)]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def registry(admin, tmp_path_factory):
    dataset_id = _upload(admin, tmp_path_factory, [HEADER, *LOCAL])
    yield dataset_id
    registry_sync.discard_preview()
    admin.delete(f"/api/datasets/{dataset_id}")


def page(client, dataset_id, **body) -> dict:
    r = client.post(f"/api/datasets/{dataset_id}/data", json={"source": "raw", "page_size": 100, **body})
    assert r.status_code == 200, r.text
    return r.json()


def by_plate(client, dataset_id) -> dict:
    data = page(client, dataset_id)
    i = data["columns"].index("mispar_rechev")
    return {row[i]: dict(zip(data["columns"], row)) for row in data["rows"]}


def test_the_missing_zeros_are_not_a_change(registry, tmp_path):
    # the government copy of exactly the same vehicles, zeros dropped
    snap = snapshot(tmp_path, [
        "1000037,404,60,לקסוס יפן,2027-02-28",
        "1000039,152,54,מרצדס בנץ,2026-05-01",
        "1000068,413,5,קיה קוריאה,2026-01-01",
        "1000099,413,5,קיה קוריאה,2026-03-03",
    ])
    report = registry_sync.preview(registry, snapshot=snap)
    assert (report["new"], report["changed"], report["removed"]) == (0, 0, 0)


def test_new_changed_and_removed_are_told_apart(registry, tmp_path):
    snap = snapshot(tmp_path, [
        "1000037,404,60,לקסוס יפן,2027-02-28",        # unchanged
        "1000039,152,54,מרצדס בנץ,2027-05-01",        # licence renewed
        "1000068,413,5,קיה ד. קוריאה,2026-01-01",     # make renamed
        "1234567,404,60,לקסוס יפן,2028-01-01",        # new
        # 01000099 is gone from the registry
    ])
    report = registry_sync.preview(registry, snapshot=snap)
    assert report["new"] == 1
    assert report["changed"] == 2
    assert report["removed"] == 1
    assert {c["column"]: c["count"] for c in report["changed_columns"]} == {
        "tokef_dt": 1, "tozeret_nm": 1,
    }
    assert {"column": "tozeret_nm", "value": "קיה ד. קוריאה", "count": 1} in report["new_values"]


def test_a_preview_changes_nothing(admin, registry, tmp_path):
    before = by_plate(admin, registry)
    snap = snapshot(tmp_path, ["1000037,404,60,לקסוס יפן,2030-01-01"])
    registry_sync.preview(registry, snapshot=snap)
    assert by_plate(admin, registry) == before


def test_applying_brings_the_changes_and_marks_them(admin, registry, tmp_path):
    snap = snapshot(tmp_path, [
        "1000037,404,60,לקסוס יפן,2027-02-28",
        "1000039,152,54,מרצדס בנץ,2027-05-01",
        "1000068,413,5,קיה קוריאה,2026-01-01",
        "1234567,404,60,לקסוס יפן,2028-01-01",
    ])
    registry_sync.preview(registry, snapshot=snap)
    result = registry_sync.apply(None, baseline=False)
    assert (result["new"], result["changed"], result["removed"]) == (1, 1, 1)

    rows = by_plate(admin, registry)
    assert rows["01000039"]["tokef_dt"] == "2027-05-01"
    assert rows["01234567"]["tozeret_cd"] == "0404", "the new row arrives padded"
    assert "01000099" in rows, "a vehicle the registry dropped is kept"
    assert len(rows) == 5

    data = page(admin, registry)
    i = data["columns"].index("mispar_rechev")
    marks = {row[i]: (a, gone) for row, a, gone in zip(data["rows"], data["arrivals"], data["removed"])}
    assert marks["01234567"] == ("new", False)
    assert marks["01000039"] == ("updated", False)
    assert marks["01000037"] == (None, False), "an unchanged vehicle is not marked updated"
    assert marks["01000099"] == (None, True)

    only_gone = page(admin, registry, only_removed=True)
    assert only_gone["total_rows"] == 1
    assert registry_sync.current_preview() is None, "an applied preview is used up"


def test_a_vehicle_that_comes_back_loses_its_mark(admin, registry, tmp_path):
    everyone = [
        "1000037,404,60,לקסוס יפן,2027-02-28",
        "1000039,152,54,מרצדס בנץ,2026-05-01",
        "1000068,413,5,קיה קוריאה,2026-01-01",
    ]
    registry_sync.preview(registry, snapshot=snapshot(tmp_path, everyone))
    registry_sync.apply(None, baseline=False)
    assert page(admin, registry, only_removed=True)["total_rows"] == 1

    back = everyone + ["1000099,413,5,קיה קוריאה,2026-03-03"]
    report = registry_sync.preview(registry, snapshot=snapshot(tmp_path, back))
    assert report["returned"] == 1 and report["removed"] == 0
    registry_sync.apply(None, baseline=False)
    assert page(admin, registry, only_removed=True)["total_rows"] == 0


def test_a_baseline_marks_nothing(admin, registry, tmp_path):
    snap = snapshot(tmp_path, [
        "1000037,404,60,לקסוס יפן,2030-01-01",
        "1000039,152,54,מרצדס בנץ,2026-05-01",
        "1000068,413,5,קיה קוריאה,2026-01-01",
        "1000099,413,5,קיה קוריאה,2026-03-03",
        "7654321,404,60,לקסוס יפן,2028-01-01",
    ])
    registry_sync.preview(registry, snapshot=snap)
    registry_sync.apply(None, baseline=True)
    data = page(admin, registry)
    assert not any(data["arrivals"]), "a baseline brings the data without the marks"
    assert by_plate(admin, registry)["01000037"]["tokef_dt"] == "2030-01-01"


def test_a_hand_correction_is_not_a_change_and_survives(admin, registry, tmp_path):
    r = admin.patch(
        f"/api/datasets/{registry}/rows",
        json={"key": ["01000037"], "changes": {"tozeret_nm": "לקסוס"}},
    )
    assert r.status_code == 200, r.text
    same_as_file = [
        "1000037,404,60,לקסוס יפן,2027-02-28",
        "1000039,152,54,מרצדס בנץ,2026-05-01",
        "1000068,413,5,קיה קוריאה,2026-01-01",
        "1000099,413,5,קיה קוריאה,2026-03-03",
    ]
    report = registry_sync.preview(registry, snapshot=snapshot(tmp_path, same_as_file))
    assert report["changed"] == 0, "the correction is not the registry changing"

    # the registry changes another field of the corrected vehicle: that is a change, and
    # the correction still wins on its own field afterwards
    renewed = ["1000037,404,60,לקסוס יפן,2029-02-28", *same_as_file[1:]]
    report = registry_sync.preview(registry, snapshot=snapshot(tmp_path, renewed))
    assert report["changed"] == 1
    registry_sync.apply(None, baseline=False)
    row = by_plate(admin, registry)["01000037"]
    assert row["tokef_dt"] == "2029-02-28"
    assert row["tozeret_nm"] == "לקסוס"


def test_a_stale_preview_is_refused(admin, registry, tmp_path):
    registry_sync.preview(registry, snapshot=snapshot(tmp_path, ["1000037,404,60,לקסוס יפן,2030-01-01"]))
    admin.patch(
        f"/api/datasets/{registry}/rows",
        json={"key": ["01000039"], "changes": {"tozeret_nm": "x"}},
    )
    with pytest.raises(registry_sync.SyncProblem) as exc:
        registry_sync.apply(None, baseline=False)
    assert exc.value.code == "registry_preview_stale"


def test_a_snapshot_with_other_columns_is_refused(registry, tmp_path):
    path = tmp_path / "snapshot.csv"
    path.write_text("_id,mispar_rechev,colour\n1,1000037,red\n", encoding="utf-8")
    with pytest.raises(registry_sync.SyncProblem) as exc:
        registry_sync.preview(registry, snapshot=path)
    assert exc.value.code == "registry_columns_differ"


def test_a_source_that_changes_while_read_is_refused(monkeypatch, tmp_path):
    stamps = iter(["2026-11-10T03:00", "2026-11-11T03:00"])
    monkeypatch.setattr(
        registry_sync, "source_info", lambda: {"last_modified": next(stamps), "total": 1}
    )
    monkeypatch.setattr(
        registry_sync, "_get",
        lambda *a, **k: {"fields": [{"id": "_id"}, {"id": "mispar_rechev"}], "records": "1,1000037\n"},
    )
    monkeypatch.setattr(registry_sync, "PAUSE_BETWEEN_PAGES", 0)
    with pytest.raises(registry_sync.SyncProblem) as exc:
        registry_sync.fetch_snapshot(tmp_path / "s.csv")
    assert exc.value.code == "registry_source_changed"


# ---- the endpoints ----


def test_only_system_managers_drive_it(viewer, editor):
    for client in (viewer, editor):
        assert client.get("/api/admin/registry-sync").status_code == 403
        assert client.post("/api/admin/registry-sync/preview").status_code == 403
        assert client.put("/api/admin/registry-sync", json={"schedule": "off"}).status_code == 403


def test_the_dataset_must_have_a_key(admin, dataset):
    r = admin.put("/api/admin/registry-sync", json={"dataset_id": dataset, "schedule": "off"})
    assert r.status_code == 409
    assert r.json()["code"] == "registry_sync_needs_key"


def test_a_schedule_needs_a_dataset(admin):
    r = admin.put("/api/admin/registry-sync", json={"dataset_id": None, "schedule": "daily"})
    assert r.status_code == 400
    assert r.json()["code"] == "registry_sync_needs_dataset"


def test_choosing_the_dataset_is_kept(admin, registry):
    r = admin.put("/api/admin/registry-sync", json={"dataset_id": registry, "schedule": "off"})
    assert r.status_code == 200, r.text
    status = admin.get("/api/admin/registry-sync").json()
    assert status["dataset_id"] == registry and status["schedule"] == "off"
    assert status["running"] is False
    admin.put("/api/admin/registry-sync", json={"dataset_id": None, "schedule": "off"})


def test_applying_without_a_preview_is_refused(admin):
    registry_sync.discard_preview()
    r = admin.post("/api/admin/registry-sync/apply", json={"baseline": False})
    assert r.status_code == 409
    assert r.json()["code"] == "registry_no_preview"


def test_a_sync_job_can_be_followed_by_its_starter_only(admin, viewer, monkeypatch, registry):
    """The settings page polls the job for its progress; a job kind missing from the
    jobs router's permission table is refused to everyone, the administrator included."""
    from app.db import catalog

    job_id = catalog.create_job(registry, "registry_preview")
    assert admin.get(f"/api/jobs/{job_id}").status_code == 200
    assert viewer.get(f"/api/jobs/{job_id}").status_code == 403


def test_a_connection_dropped_mid_page_is_retried(monkeypatch):
    """Found on the first full pull: an SSL record failure while reading a page body is
    not a URLError, and it ended the whole run twenty pages in."""
    import io as _io
    import json as _json
    import ssl

    calls = {"n": 0}

    class Body(_io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def flaky(request, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ssl.SSLError("record layer failure")
        return Body(_json.dumps({"success": True, "result": {"ok": 1}}).encode())

    monkeypatch.setattr(registry_sync.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(registry_sync.time, "sleep", lambda _s: None)
    assert registry_sync._get("datastore_search", {}) == {"ok": 1}
    assert calls["n"] == 2
