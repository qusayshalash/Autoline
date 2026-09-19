"""Which records arrived recently, and telling a new one from an updated one.

Scrolling to the end is not a way to see what a batch brought: `fetch_page` adds no
ORDER BY unless one is asked for, and an upsert moves the record it replaces to the end
as well - so the last page is a mixture of arrived and merely re-written, in an order
nothing promises to keep.

These check the three things that make the mark trustworthy instead: that new and updated
are told apart, that replaying a batch is not arriving, and that the record expires.
"""

import pytest
from conftest import wait_for_job
from helpers import rows_as_dicts, total

BASE_ROWS = 20


def csv_bytes(rows: list[str], header: str = "plate,make,year") -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


@pytest.fixture(scope="module")
def fleet(admin, tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("arrivals") / "fleet.csv"
    path.write_bytes(
        csv_bytes([f"{80000 + i:08d},KIA,{2000 + i}" for i in range(BASE_ROWS)])
    )
    with open(path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("fleet.csv", f, "text/csv")})
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    assert admin.put(
        f"/api/datasets/{dataset_id}/key", json={"columns": ["plate"]}
    ).status_code == 200
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


def append(client, dataset_id, data: bytes):
    return client.post(
        f"/api/datasets/{dataset_id}/append", files={"file": ("batch.csv", data, "text/csv")}
    )


def page(client, dataset_id, **body) -> dict:
    r = client.post(f"/api/datasets/{dataset_id}/data", json={"source": "raw", **body})
    assert r.status_code == 200, r.text
    return r.json()


EXISTING = f"{80000:08d}"
BROUGHT = "00099001"


def test_nothing_has_arrived_before_a_batch(admin, fleet):
    assert admin.get(f"/api/datasets/{fleet}/arrivals").json() is None
    body = page(admin, fleet)
    assert body["arrivals"] == [None] * len(body["rows"]), "no batch, no marks"


def test_a_batch_marks_what_it_brought(admin, fleet):
    r = append(admin, fleet, csv_bytes([f"{EXISTING},KIA,2030", f"{BROUGHT},HONDA,2022"]))
    assert r.status_code == 200, r.text

    summary = admin.get(f"/api/datasets/{fleet}/arrivals").json()
    assert summary["new"] == 1, summary
    assert summary["updated"] == 1, summary
    assert summary["latest_at"], "an arrival with no time cannot expire"
    assert summary["window_days"] >= 1


def test_the_two_are_told_apart_on_the_page(admin, fleet):
    """One vehicle was already here and one was not, and a reader scanning the page
    should not have to remember which."""
    body = page(admin, fleet, page_size=200)
    plate_at = body["columns"].index("plate")
    marks = {row[plate_at]: mark for row, mark in zip(body["rows"], body["arrivals"])}

    assert marks[EXISTING] == "updated"
    assert marks[BROUGHT] == "new"
    untouched = [p for p, m in marks.items() if m is None]
    assert len(untouched) == BASE_ROWS - 1, "only what the batch touched is marked"


def test_the_filter_keeps_only_what_arrived(admin, fleet):
    """The reason the filter exists: reviewing a delivery by scanning four million rows
    for a colour is not reviewing."""
    everything = total(admin, fleet, source="raw")
    recent = page(admin, fleet, only_recent=True, page_size=200)
    assert recent["total_rows"] == 2
    assert recent["total_rows"] < everything
    plates = {row[recent["columns"].index("plate")] for row in recent["rows"]}
    assert plates == {EXISTING, BROUGHT}


def test_the_filter_combines_with_a_search(admin, fleet):
    recent = page(admin, fleet, only_recent=True, search="HONDA", page_size=200)
    assert recent["total_rows"] == 1
    assert recent["rows"][0][recent["columns"].index("plate")] == BROUGHT


def test_replaying_a_batch_is_not_arriving(admin, fleet):
    """A re-import replays every stored batch. Marking them again would make it look to
    the reader like a fresh delivery of everything the dataset has ever received."""
    before = admin.get(f"/api/datasets/{fleet}/arrivals").json()
    r = admin.post(
        f"/api/datasets/{fleet}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"

    after = admin.get(f"/api/datasets/{fleet}/arrivals").json()
    assert after["new"] == before["new"]
    assert after["updated"] == before["updated"]
    assert after["latest_at"] == before["latest_at"], "the clock must not have restarted"


def test_a_record_arriving_twice_keeps_its_first_arrival(admin, fleet):
    """To a reader, a vehicle that came last Tuesday and was restated today is still the
    vehicle that came last Tuesday."""
    before = admin.get(f"/api/datasets/{fleet}/arrivals").json()
    r = append(admin, fleet, csv_bytes([f"{BROUGHT},HONDA,2023"]))
    assert r.status_code == 200, r.text

    after = admin.get(f"/api/datasets/{fleet}/arrivals").json()
    assert after["new"] + after["updated"] == before["new"] + before["updated"], (
        "the same record must not be counted as two arrivals"
    )
    body = page(admin, fleet, only_recent=True, page_size=200)
    marks = dict(zip((r[body["columns"].index("plate")] for r in body["rows"]), body["arrivals"]))
    assert marks[BROUGHT] == "new", "it did not stop being the record that arrived"


def test_the_mark_expires(admin, fleet):
    """The point of the window. Set it to its floor and reach past it with the clock the
    service itself uses, rather than waiting a day."""
    from datetime import timedelta

    from app.db.connection import datasets
    from app.services import arrivals

    assert admin.put("/api/datasets/arrivals/window", json={"days": 1}).status_code == 200

    # age every recorded arrival past the window
    with datasets.write_lock(fleet):
        datasets.cursor(fleet).execute(
            f"UPDATE {arrivals.TABLE} SET added_at = ?",
            [arrivals.clocks.now() - timedelta(days=2)],
        )

    # the sweep runs on the next append
    assert append(admin, fleet, csv_bytes(["00099777,SEAT,2024"])).status_code == 200

    summary = admin.get(f"/api/datasets/{fleet}/arrivals").json()
    assert summary["new"] == 1, "only the batch just appended should still be marked"
    assert summary["updated"] == 0

    body = page(admin, fleet, page_size=200)
    marks = dict(zip((r[body["columns"].index("plate")] for r in body["rows"]), body["arrivals"]))
    assert marks[EXISTING] is None, "an arrival past the window stops being pointed at"
    assert marks["00099777"] == "new"


def test_the_window_has_a_floor_and_a_ceiling(admin):
    assert admin.put("/api/datasets/arrivals/window", json={"days": 0}).status_code == 422
    assert admin.put("/api/datasets/arrivals/window", json={"days": 400}).status_code == 422


def test_changing_the_window_needs_system_manage(editor, viewer):
    assert editor.put("/api/datasets/arrivals/window", json={"days": 7}).status_code == 403
    assert viewer.put("/api/datasets/arrivals/window", json={"days": 7}).status_code == 403


def test_a_dataset_with_no_key_is_marked_by_nothing(admin, dataset):
    """Nothing says which record is which, so nothing can be said to have arrived - and
    the filter returns nothing rather than everything."""
    assert admin.get(f"/api/datasets/{dataset}/arrivals").json() is None
    body = page(admin, dataset, only_recent=True)
    assert body["total_rows"] == 0, "unknown must not be read as 'all of it'"
