"""Which columns identify a record, and refusing the ones that do not.

Everything downstream rests on this. A key that is not unique makes "replace the record
that is already there" ambiguous and "correct this cell" a coin toss between two rows,
so the check is not a formality - it is the thing that makes the rest safe.

The synthetic fixture is built with two byte-identical rows precisely because the real
4.1M-row registry has them. A column that looks like an identifier in a sample is not
one, and this is where that gets caught.
"""

import pytest
import synthetic


@pytest.fixture(scope="module")
def keyed(admin, csv_path) -> str:
    """A dataset of its own: the shared one is read by the whole suite, and setting a
    key on it would change what other tests see."""
    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("keys.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={
            "encoding": synthetic.ENCODING,
            "delimiter": synthetic.DELIMITER,
            "has_header": True,
        },
    )
    from conftest import wait_for_job

    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


@pytest.fixture(scope="module")
def clean_dataset(admin, tmp_path_factory) -> str:
    """A small file with genuinely unique identifiers.

    The synthetic fixture cannot serve here: it contains two byte-identical rows on
    purpose, so *no* combination of its columns is unique and the accepting path would
    never be exercised - it would skip, which is a test that passes by not running.
    """
    path = tmp_path_factory.mktemp("keys") / "unique.csv"
    path.write_text(
        "plate,make,year\n" + "".join(f"{1000 + i:08d},KIA,{2000 + i}\n" for i in range(50)),
        encoding="utf-8",
    )
    with open(path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("unique.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    from conftest import wait_for_job

    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


def check(client, dataset_id, *columns):
    return client.get(
        f"/api/datasets/{dataset_id}/key/check", params={"columns": ",".join(columns)}
    )


def test_the_fixture_really_has_a_repeated_identifier(oracle):
    """A guard on the guard: if the duplicate pair ever left the fixture, the refusal
    test below would pass by having nothing to refuse."""
    ids = [row["mispar_rechev"] for row in oracle]
    assert len(ids) != len(set(ids)), "the fixture is supposed to contain a duplicate"


def test_a_repeated_identifier_is_refused_with_the_count(admin, keyed):
    r = check(admin, keyed, "mispar_rechev")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unique"] is False
    assert body["duplicate_rows"] >= 1
    assert body["total_rows"] == body["distinct_keys"] + body["duplicate_rows"]

    # and setting it is refused, with the code the interface translates
    r = admin.put(f"/api/datasets/{keyed}/key", json={"columns": ["mispar_rechev"]})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "key_not_unique"


def test_the_dataset_says_it_has_no_key_until_one_is_accepted(admin, keyed):
    assert admin.get(f"/api/datasets/{keyed}").json()["key_columns"] == []


def test_checking_a_key_changes_nothing(admin, keyed):
    """The point of a dry run. An administrator tries a column, sees the duplicates, and
    tries a different one - none of which should leave the dataset altered."""
    before = admin.get(f"/api/datasets/{keyed}").json()
    check(admin, keyed, "mispar_rechev")
    check(admin, keyed, "tozeret_nm")
    after = admin.get(f"/api/datasets/{keyed}").json()
    assert after["key_columns"] == before["key_columns"] == []
    assert after["row_count_raw"] == before["row_count_raw"]


def test_a_column_that_does_not_exist_is_named(admin, keyed):
    r = check(admin, keyed, "not_a_column")
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "key_unknown_column"


def test_a_key_cannot_repeat_a_column(admin, keyed):
    r = check(admin, keyed, "mispar_rechev", "mispar_rechev")
    assert r.status_code == 422
    assert r.json()["code"] == "key_repeated"


def test_a_key_has_a_column_limit(admin, keyed):
    r = check(admin, keyed, *synthetic.COLUMNS[:5])
    assert r.status_code == 422
    assert r.json()["code"] == "key_max_columns"


def test_a_unique_key_is_accepted_and_remembered(admin, clean_dataset):
    r = check(admin, clean_dataset, "plate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unique"] is True
    assert body["total_rows"] == body["distinct_keys"] == 50
    assert body["duplicate_rows"] == 0

    r = admin.put(f"/api/datasets/{clean_dataset}/key", json={"columns": ["plate"]})
    assert r.status_code == 200, r.text
    assert r.json()["key_columns"] == ["plate"]
    assert admin.get(f"/api/datasets/{clean_dataset}").json()["key_columns"] == ["plate"]


def test_a_composite_key_is_accepted(admin, clean_dataset):
    r = check(admin, clean_dataset, "plate", "year")
    assert r.status_code == 200, r.text
    assert r.json()["unique"] is True


def test_a_column_that_repeats_is_refused_even_in_a_small_file(admin, clean_dataset):
    """Every row shares a maker, so `make` identifies nothing. The count is what tells
    the reader that, rather than a bare refusal."""
    r = check(admin, clean_dataset, "make")
    assert r.status_code == 200, r.text
    assert r.json()["unique"] is False
    assert r.json()["distinct_keys"] == 1

    r = admin.put(f"/api/datasets/{clean_dataset}/key", json={"columns": ["make"]})
    assert r.status_code == 422
    assert r.json()["code"] == "key_not_unique"


def test_a_refused_key_does_not_replace_the_one_already_set(admin, clean_dataset):
    """The dataset had a working key before that refusal; it must still have it."""
    assert admin.get(f"/api/datasets/{clean_dataset}").json()["key_columns"] == ["plate"]


def test_clearing_the_key_leaves_the_data_alone(admin, clean_dataset):
    before = admin.get(f"/api/datasets/{clean_dataset}").json()["row_count_raw"]
    r = admin.delete(f"/api/datasets/{clean_dataset}/key")
    assert r.status_code == 200, r.text
    assert r.json()["key_columns"] == []
    assert admin.get(f"/api/datasets/{clean_dataset}").json()["row_count_raw"] == before
    # put it back for whatever runs after this
    admin.put(f"/api/datasets/{clean_dataset}/key", json={"columns": ["plate"]})


# ---- authorization ---------------------------------------------------------------------

def test_an_editor_cannot_set_the_key(editor, keyed):
    """Hiding the control is not the protection. The editor uploads and cleans; deciding
    what identifies a record is the administrator's."""
    r = editor.put(f"/api/datasets/{keyed}/key", json={"columns": ["mispar_rechev"]})
    assert r.status_code == 403, r.text


def test_a_viewer_cannot_check_a_key(viewer, keyed):
    r = check(viewer, keyed, "mispar_rechev")
    assert r.status_code == 403, r.text


def test_nobody_anonymous_can(anon, keyed):
    assert check(anon, keyed, "mispar_rechev").status_code == 401
