"""Correcting a record, and the correction surviving everything that rebuilds the table.

The whole point of keeping corrections in a table of their own is that `raw_data` is not
durable: the import rebuilds it from the uploaded file with `CREATE TABLE AS`, and every
cleaning run rebuilds `cleaned_data` from that. An edit written only into the table would
be there until the next import and then be gone, with nothing on screen to say so.

So the tests that matter here are not "does an UPDATE work" - they are the three that
tear the table down and check the correction came back.
"""

import pytest
from conftest import wait_for_job
from helpers import rows_as_dicts

ROWS = 40


@pytest.fixture(scope="module")
def corrected(admin, tmp_path_factory) -> str:
    """A small dataset with a real identifier and one obviously wrong value."""
    path = tmp_path_factory.mktemp("corrections") / "fleet.csv"
    lines = ["plate,make,year,city"]
    for i in range(ROWS):
        year = "not-a-year" if i == 7 else str(2000 + i % 25)
        lines.append(f"{5000 + i:08d},{['KIA', 'TOYOTA'][i % 2]},{year},رام الله")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with open(path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("fleet.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
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


BAD_PLATE = f"{5007:08d}"


def value_of(client, dataset_id, plate, column, source="raw"):
    rows = rows_as_dicts(
        client, dataset_id, source=source,
        filters=[{"column": "plate", "op": "eq", "value": plate}],
    )
    assert len(rows) == 1, rows
    return rows[0][column]


def test_the_fixture_starts_wrong(admin, corrected):
    assert value_of(admin, corrected, BAD_PLATE, "year") == "not-a-year"


def test_a_correction_shows_in_the_data(admin, corrected):
    r = admin.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": [BAD_PLATE], "changes": {"year": "2013"}},
    )
    assert r.status_code == 200, r.text
    assert value_of(admin, corrected, BAD_PLATE, "year") == "2013"


def test_the_correction_remembers_what_the_file_said(admin, corrected):
    r = admin.get(f"/api/datasets/{corrected}/corrections")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["column"] == "year"
    assert entry["old_value"] == "not-a-year"
    assert entry["new_value"] == "2013"
    assert entry["row_key"] == [BAD_PLATE]
    assert entry["actor"]
    assert entry["edited_at"], "an audit entry with no time is not an audit entry"


def test_correcting_twice_still_remembers_the_file_not_the_last_edit(admin, corrected):
    """Otherwise the original is lost after the second edit, and the trail describes a
    value that never came from anywhere."""
    admin.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": [BAD_PLATE], "changes": {"year": "2014"}},
    )
    entry = admin.get(f"/api/datasets/{corrected}/corrections").json()["items"][0]
    assert entry["old_value"] == "not-a-year"
    assert entry["new_value"] == "2014"
    assert admin.get(f"/api/datasets/{corrected}/corrections").json()["total"] == 1


def test_the_correction_survives_a_clean(admin, corrected):
    """cleaned_data is built from raw_data, which already carries the correction - so
    this passes by construction, and would stop passing the day the two are built from
    the file independently."""
    r = admin.post(f"/api/datasets/{corrected}/clean", json={"dedupe": False})
    assert r.status_code == 200, r.text
    assert value_of(admin, corrected, BAD_PLATE, "year", source="cleaned") == "2014"


def test_the_correction_survives_a_re_import(admin, corrected):
    """The one that matters. The import drops raw_data and builds it again from the
    uploaded file, which still says "not-a-year"."""
    r = admin.post(
        f"/api/datasets/{corrected}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    assert value_of(admin, corrected, BAD_PLATE, "year") == "2014"
    assert admin.get(f"/api/datasets/{corrected}/corrections").json()["total"] == 1


def test_reverting_puts_the_file_s_own_value_back(admin, corrected):
    r = admin.request(
        "DELETE",
        f"/api/datasets/{corrected}/corrections",
        json={"key": [BAD_PLATE], "changes": {"year": ""}},
    )
    assert r.status_code == 200, r.text
    assert value_of(admin, corrected, BAD_PLATE, "year") == "not-a-year"
    assert admin.get(f"/api/datasets/{corrected}/corrections").json()["total"] == 0


def test_reverting_what_was_never_corrected_is_a_404(admin, corrected):
    r = admin.request(
        "DELETE",
        f"/api/datasets/{corrected}/corrections",
        json={"key": [BAD_PLATE], "changes": {"year": ""}},
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "correction_not_found"


# ---- what must be refused ---------------------------------------------------------------

def test_the_key_column_cannot_be_corrected(admin, corrected):
    """Changing it would change which record this is: the correction could no longer be
    addressed, and a later batch would stop recognising the row."""
    r = admin.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": [BAD_PLATE], "changes": {"plate": "99999999"}},
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "cannot_edit_key_column"
    assert value_of(admin, corrected, BAD_PLATE, "make") in ("KIA", "TOYOTA")


def test_a_record_that_is_not_there(admin, corrected):
    r = admin.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": ["00000000"], "changes": {"year": "2013"}},
    )
    assert r.status_code == 404
    assert r.json()["code"] == "row_not_found"


def test_a_column_that_is_not_there(admin, corrected):
    r = admin.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": [BAD_PLATE], "changes": {"nonsense": "x"}},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "unknown_column"


def test_a_key_of_the_wrong_length(admin, corrected):
    r = admin.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": [BAD_PLATE, "extra"], "changes": {"year": "2013"}},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "key_wrong_length"


def test_a_dataset_with_no_key_says_so_rather_than_guessing(admin, dataset):
    """The shared fixture has never had a key set."""
    r = admin.patch(
        f"/api/datasets/{dataset}/rows",
        json={"key": ["00009042"], "changes": {"tozeret_nm": "x"}},
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "dataset_has_no_key"


def test_an_unknown_field_in_the_body_is_refused(admin, corrected):
    """Incoming forbids extras, so a typo cannot be read as "change nothing"."""
    r = admin.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": [BAD_PLATE], "changes": {"year": "2013"}, "reason": "typo"},
    )
    assert r.status_code == 422, r.text


# ---- authorization ------------------------------------------------------------------------

def test_an_editor_cannot_correct_a_record(editor, corrected):
    """Admin only, decided deliberately: a correction overwrites what the source file
    says about a real vehicle. Asserted against the API, not against a hidden button."""
    r = editor.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": [BAD_PLATE], "changes": {"year": "1999"}},
    )
    assert r.status_code == 403, r.text


def test_a_viewer_cannot_read_the_corrections(viewer, corrected):
    assert viewer.get(f"/api/datasets/{corrected}/corrections").status_code == 403


def test_an_editor_cannot_revert_one(editor, corrected):
    r = editor.request(
        "DELETE",
        f"/api/datasets/{corrected}/corrections",
        json={"key": [BAD_PLATE], "changes": {"year": ""}},
    )
    assert r.status_code == 403, r.text


def test_nobody_anonymous_can(anon, corrected):
    r = anon.patch(
        f"/api/datasets/{corrected}/rows",
        json={"key": [BAD_PLATE], "changes": {"year": "1999"}},
    )
    assert r.status_code == 401, r.text
