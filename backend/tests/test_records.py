"""The vehicle card: one record by its key, with its batch mark and its corrections.

The record itself is readable by anyone who can read the grid. Who corrected what is
shown only to those who can correct, the same line the grid draws for its marks.
"""

import pytest
from conftest import wait_for_job

ROWS = 12


def _upload(admin, tmp_path_factory, name: str, lines: list[str]) -> str:
    path = tmp_path_factory.mktemp("records") / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": (name, f, "text/csv")})
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    return dataset_id


@pytest.fixture(scope="module")
def cards(admin, tmp_path_factory) -> str:
    lines = ["plate,make,year,color"]
    lines += [f"{70000 + i:08d},{['KIA', 'TOYOTA'][i % 2]},{2010 + i},לבן" for i in range(ROWS)]
    dataset_id = _upload(admin, tmp_path_factory, "cards.csv", lines)
    assert admin.put(
        f"/api/datasets/{dataset_id}/key", json={"columns": ["plate"]}
    ).status_code == 200
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


PLATE = f"{70003:08d}"


def card(client, dataset_id, *key):
    return client.get(f"/api/datasets/{dataset_id}/record", params=[("key", k) for k in key])


def test_the_whole_record_comes_back(viewer, cards):
    r = card(viewer, cards, PLATE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["columns"] == ["plate", "make", "year", "color"]
    assert dict(zip(body["columns"], body["values"])) == {
        "plate": PLATE, "make": "TOYOTA", "year": "2013", "color": "לבן",
    }
    assert body["key_columns"] == ["plate"] and body["key"] == [PLATE]
    assert body["arrival"] is None


def test_a_missing_record_is_404(viewer, cards):
    r = card(viewer, cards, "99999999")
    assert r.status_code == 404
    assert r.json()["code"] == "row_not_found"


def test_the_key_must_have_the_right_length(viewer, cards):
    r = card(viewer, cards, PLATE, "extra")
    assert r.status_code == 400
    assert r.json()["code"] == "key_wrong_length"


def test_signed_out_nothing(anon, cards):
    assert card(anon, cards, PLATE).status_code == 401


def test_a_file_without_a_key_cannot_open_a_record(viewer, dataset):
    r = card(viewer, dataset, "anything")
    assert r.status_code == 409
    assert r.json()["code"] == "dataset_has_no_record_key"


def test_corrections_show_to_whoever_can_correct(admin, viewer, cards):
    r = admin.patch(
        f"/api/datasets/{cards}/rows", json={"key": [PLATE], "changes": {"color": "שחור"}}
    )
    assert r.status_code == 200, r.text

    seen = card(admin, cards, PLATE).json()
    assert dict(zip(seen["columns"], seen["values"]))["color"] == "שחור"
    [entry] = seen["corrections"]
    assert entry["column"] == "color"
    assert entry["old_value"] == "לבן" and entry["new_value"] == "שחור"
    assert entry["actor"] == "test_admin"

    # the viewer reads the corrected value, but not who changed it or from what
    seen = card(viewer, cards, PLATE).json()
    assert dict(zip(seen["columns"], seen["values"]))["color"] == "שחור"
    assert seen["corrections"] is None


def test_a_record_a_batch_brought_says_so(admin, cards):
    batch = "plate,make,year,color\n" + f"{70001:08d},KIA,2099,אדום\n" + "00071234,KIA,2024,כחול\n"
    r = admin.post(
        f"/api/datasets/{cards}/append",
        files={"file": ("batch.csv", batch.encode("utf-8"), "text/csv")},
    )
    assert r.status_code in (200, 202), r.text
    if "id" in r.json() and r.json().get("status") in ("pending", "running"):
        wait_for_job(admin, r.json()["id"])

    replaced = card(admin, cards, f"{70001:08d}").json()
    assert replaced["arrival"]["kind"] == "updated"
    assert replaced["arrival"]["added_at"]
    added = card(admin, cards, "00071234").json()
    assert added["arrival"]["kind"] == "new"
    untouched = card(admin, cards, f"{70002:08d}").json()
    assert untouched["arrival"] is None
