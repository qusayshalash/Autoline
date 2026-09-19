"""Adding a later batch of the same data to a dataset that already exists.

Three things have to hold, and only the first is obvious:

  * the new records arrive, and a record that was already there is replaced rather than
    duplicated - which needs a key;
  * the cleaned table is rebuilt, or a reader looking at the cleaned source sees a row
    count that silently stopped moving;
  * re-importing does not lose the batch. `raw_data` is rebuilt from the original upload
    alone, so a batch that lived only in the table would vanish without a trace.
"""

import pytest
from conftest import wait_for_job
from helpers import rows_as_dicts, total

BASE_ROWS = 30


def csv_bytes(rows: list[str], header: str = "plate,make,year") -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


@pytest.fixture(scope="module")
def fleet(admin, tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("appending") / "fleet.csv"
    path.write_bytes(
        csv_bytes([f"{7000 + i:08d},KIA,{2000 + i % 20}" for i in range(BASE_ROWS)])
    )
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


def append(client, dataset_id, data: bytes, name: str = "batch.csv", **form):
    return client.post(
        f"/api/datasets/{dataset_id}/append",
        files={"file": (name, data, "text/csv")},
        data=form or None,
    )


def year_of(client, dataset_id, plate, source="raw"):
    rows = rows_as_dicts(
        client, dataset_id, source=source,
        filters=[{"column": "plate", "op": "eq", "value": plate}],
    )
    return [row["year"] for row in rows]


EXISTING = f"{7000:08d}"
NEW = "99990001"


def test_the_base_is_what_the_fixture_says(admin, fleet):
    assert admin.get(f"/api/datasets/{fleet}").json()["row_count_raw"] == BASE_ROWS


def test_a_batch_adds_the_new_and_replaces_the_existing(admin, fleet):
    r = append(admin, fleet, csv_bytes([f"{EXISTING},KIA,2024", f"{NEW},HONDA,2022"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows_replaced"] == 1
    assert body["rows_added"] == 1
    assert body["row_count_raw"] == BASE_ROWS + 1, "the existing plate must not be doubled"

    assert year_of(admin, fleet, EXISTING) == ["2024"], "the newer statement should win"
    assert year_of(admin, fleet, NEW) == ["2022"]


def test_the_count_on_the_dataset_record_matches(admin, fleet):
    row = admin.get(f"/api/datasets/{fleet}").json()
    assert row["row_count_raw"] == total(admin, fleet, source="raw")


def test_a_batch_in_a_different_column_order_is_accepted(admin, fleet):
    """The rows are reordered on the way in, so only the set of names has to match."""
    before = total(admin, fleet, source="raw")
    r = append(
        admin, fleet,
        csv_bytes(["2021,TOYOTA,99990002"], header="year,make,plate"),
    )
    assert r.status_code == 200, r.text
    assert total(admin, fleet, source="raw") == before + 1
    assert year_of(admin, fleet, "99990002") == ["2021"]


HEBREW_BATCH = "plate;make;year\n99990003;מרצדס;2020\n".encode("cp1255")


def test_a_differently_encoded_batch_is_refused_rather_than_mangled(admin, fleet):
    """Detection is not attempted, and that is the point.

    charset-normalizer answers "johab" - a Korean codepage - for these 36 bytes, because
    six Hebrew characters are not enough evidence for anything. Its multi-byte sequences
    then swallow the ";" and merge two columns into one, so the row lands with the maker
    reading 懊鬪已2020 and the year empty. The dataset's own encoding is used instead, and
    the column check refuses what does not parse under it.
    """
    before = total(admin, fleet, source="raw")
    r = append(admin, fleet, HEBREW_BATCH)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "append_columns_differ"
    assert total(admin, fleet, source="raw") == before


def test_a_batch_in_a_different_encoding_is_accepted_when_the_caller_says_so(admin, fleet):
    """The override exists for a batch that genuinely differs from the first file."""
    before = total(admin, fleet, source="raw")
    r = append(admin, fleet, HEBREW_BATCH, encoding="cp1255", delimiter=";")
    assert r.status_code == 200, r.text
    assert total(admin, fleet, source="raw") == before + 1
    rows = rows_as_dicts(
        admin, fleet, source="raw",
        filters=[{"column": "plate", "op": "eq", "value": "99990003"}],
    )
    assert rows[0]["make"] == "מרצדס", "the Hebrew must survive the transcode"
    assert rows[0]["year"] == "2020", "and the delimiter must not have been swallowed"


def test_a_file_of_the_wrong_shape_is_refused_and_names_what_differs(admin, fleet):
    before = total(admin, fleet, source="raw")
    r = append(admin, fleet, csv_bytes(["99990004,FIAT"], header="plate,make"))
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "append_columns_differ"
    assert total(admin, fleet, source="raw") == before, "a refused batch must change nothing"


def test_a_refused_batch_leaves_no_file_behind_to_replay(admin, fleet):
    """A half-written batch on disk would be replayed on the next import, which would
    make a rejected file land after all - the worst of both outcomes."""
    before = total(admin, fleet, source="raw")
    r = admin.post(
        f"/api/datasets/{fleet}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    assert total(admin, fleet, source="raw") == before


def test_the_batches_survive_a_re_import(admin, fleet):
    """The import rebuilds raw_data from the first upload, which knows nothing about any
    of this. The batches are replayed from disk afterwards."""
    assert year_of(admin, fleet, NEW) == ["2022"], "the appended record came back"
    assert year_of(admin, fleet, EXISTING) == ["2024"], "and so did the replacement"
    assert year_of(admin, fleet, "99990003") == ["2020"]


def test_the_cleaned_table_is_rebuilt_so_it_sees_the_new_rows(admin, fleet):
    r = admin.post(f"/api/datasets/{fleet}/clean", json={"dedupe": False})
    assert r.status_code == 200, r.text
    cleaned_before = total(admin, fleet, source="cleaned")

    r = append(admin, fleet, csv_bytes(["99990005,SKODA,2019"]))
    assert r.status_code == 200, r.text
    assert r.json()["cleaned_rebuilt"] is True
    assert total(admin, fleet, source="cleaned") == cleaned_before + 1
    assert year_of(admin, fleet, "99990005", source="cleaned") == ["2019"]


def test_a_correction_and_a_batch_coexist(admin, fleet):
    """Both are replayed after a rebuild, and in the order that leaves the correction on
    top - a batch that restates a record the reader had corrected would otherwise undo
    the correction on every import."""
    admin.patch(
        f"/api/datasets/{fleet}/rows",
        json={"key": [NEW], "changes": {"make": "HONDA CIVIC"}},
    )
    r = admin.post(
        f"/api/datasets/{fleet}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    rows = rows_as_dicts(
        admin, fleet, source="raw",
        filters=[{"column": "plate", "op": "eq", "value": NEW}],
    )
    assert rows[0]["make"] == "HONDA CIVIC"
    assert rows[0]["year"] == "2022", "the batch is still there under the correction"


# ---- without a key ----------------------------------------------------------------------

def test_without_a_key_a_batch_only_adds(admin, fleet):
    """Nothing says what a repeated record is, so nothing is replaced - which is the
    honest behaviour, and why the interface reports it."""
    admin.delete(f"/api/datasets/{fleet}/key")
    before = total(admin, fleet, source="raw")
    r = append(admin, fleet, csv_bytes([f"{EXISTING},KIA,2030"]))
    assert r.status_code == 200, r.text
    assert r.json()["rows_replaced"] == 0
    assert total(admin, fleet, source="raw") == before + 1
    assert sorted(year_of(admin, fleet, EXISTING)) == ["2024", "2030"]
    admin.put(f"/api/datasets/{fleet}/key", json={"columns": ["plate"]})


# ---- authorization ------------------------------------------------------------------------

def test_an_editor_may_append(editor, fleet):
    """Appending is an import, and importing is what an editor does. Deciding whether it
    replaces - that is, setting the key - is the administrator's, and tested elsewhere."""
    before = total(editor, fleet, source="raw")
    r = append(editor, fleet, csv_bytes(["99990006,MAZDA,2018"]))
    assert r.status_code == 200, r.text
    assert total(editor, fleet, source="raw") == before + 1


def test_a_viewer_cannot_append(viewer, fleet):
    assert append(viewer, fleet, csv_bytes(["99990007,OPEL,2017"])).status_code == 403


def test_nobody_anonymous_can(anon, fleet):
    assert append(anon, fleet, csv_bytes(["99990008,SEAT,2016"])).status_code == 401
