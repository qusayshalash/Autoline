"""The vehicle catalog: one car, by plate or chassis number, at /catalog.

The lookup has to accept a number the way people write it - the registry stores
every plate zero-padded to eight characters, and 45% of real plates start with that zero -
and find it in whichever dataset holds it.

(The second half, a Wikipedia photo of the model, was removed on 2026-11-18 at Qusay's
request; its code and tests are in the history before that date.)
"""

import pytest
from app.services import vehicle_lookup


# ---- reading what was typed -----------------------------------------------------------


@pytest.mark.parametrize(
    "typed,plate",
    [
        ("4910766", "04910766"),      # seven digits, as printed
        ("49-107-66", "04910766"),    # with the plate's own dashes
        ("49 107 66", "04910766"),
        ("04910766", "04910766"),     # as stored
        ("491-07-665", "49107665"),   # eight digits
        ("  12345678 ", "12345678"),
    ],
)
def test_a_plate_is_read_however_it_was_written(typed, plate):
    assert vehicle_lookup.interpret(typed) == (plate, None)


@pytest.mark.parametrize(
    "typed,chassis",
    [
        ("knab2512aft000001", "KNAB2512AFT000001"),   # the file is all upper case
        ("KNAB 2512 AFT 000001", "KNAB2512AFT000001"),
        ("123456789012", "123456789012"),            # too long for a plate
    ],
)
def test_a_chassis_number_is_read_however_it_was_written(typed, chassis):
    assert vehicle_lookup.interpret(typed) == (None, chassis)


@pytest.mark.parametrize("typed", ["", "   ", "كيا", "12;DROP", "ab%cd"])
def test_what_is_neither_is_said_to_be_neither(typed):
    assert vehicle_lookup.interpret(typed) == (None, None)


# ---- finding it -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry(admin) -> str:
    """Three vehicles in the registry's own shape - including one seven-digit plate,
    stored with its leading zero, and one chassis number that occurs twice, as two real
    ones do in the 4.1M-row file."""
    from conftest import wait_for_job

    body = (
        "mispar_rechev,tozeret_nm,kinuy_mishari,shnat_yitzur,misgeret,tokef_dt\n"
        "04910766,קיה קוריאה,PICANTO,2015,KNAB2512AFT000001,2027-01-29\n"
        "49107665,טויוטה יפן,COROLLA,2019,JTDBR32E000000002,2020-03-03\n"
        "01002085,מאזדה יפן,3,2012,JTDBR32E000000002,2024-06-29\n"
    ).encode("utf-8")
    r = admin.post("/api/datasets/upload", files={"file": ("registry.csv", body, "text/csv")})
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


def find(client, q):
    r = client.get("/api/catalog/lookup", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()


def field(match, column):
    return match["values"][match["columns"].index(column)]


def test_a_seven_digit_plate_finds_the_stored_eight(admin, registry):
    """The case the whole normalising is for: typed as printed, stored with a zero."""
    out = find(admin, "49-107-66")
    assert out["kind"] == "plate" and out["normalized"] == "04910766"
    mine = [m for m in out["matches"] if m["dataset_id"] == registry]
    assert len(mine) == 1
    assert field(mine[0], "kinuy_mishari") == "PICANTO"


def test_the_whole_row_comes_back(admin, registry):
    """Every column the dataset has - the page groups them, it does not choose them."""
    match = next(m for m in find(admin, "4910766")["matches"] if m["dataset_id"] == registry)
    assert match["columns"][:3] == ["mispar_rechev", "tozeret_nm", "kinuy_mishari"]
    assert field(match, "tozeret_nm") == "קיה קוריאה"
    assert match["dataset_name"] == "registry.csv"


def test_a_chassis_number_is_found_in_any_case(admin, registry):
    out = find(admin, "knab2512aft000001")
    assert out["kind"] == "chassis"
    assert [field(m, "mispar_rechev") for m in out["matches"] if m["dataset_id"] == registry] == ["04910766"]


def test_a_shared_chassis_number_returns_every_vehicle(admin, registry):
    """Two real chassis numbers occur twice in the registry. Showing one would be
    choosing for the reader which car they meant."""
    out = find(admin, "JTDBR32E000000002")
    plates = sorted(field(m, "mispar_rechev") for m in out["matches"] if m["dataset_id"] == registry)
    assert plates == ["01002085", "49107665"]


def test_an_unknown_number_is_an_empty_answer_not_an_error(admin, registry):
    out = find(admin, "9999999")
    assert out["kind"] == "plate" and out["matches"] == []


def test_a_dataset_without_the_columns_is_skipped(admin, registry, dataset):
    """The synthetic fixture dataset has plates; others in the session do not. None of
    them may turn a lookup into an error."""
    assert find(admin, "4910766")["kind"] == "plate"


def test_what_is_neither_returns_nothing(admin, registry):
    out = find(admin, "كيا")
    assert out["kind"] is None and out["matches"] == []


def test_corrections_are_part_of_the_answer(admin, registry):
    """It reads raw_data, which is the file plus every correction - so a fixed licence
    date is what the catalog shows."""
    assert admin.put(f"/api/datasets/{registry}/key", json={"columns": ["mispar_rechev"]}).status_code == 200
    r = admin.patch(
        f"/api/datasets/{registry}/rows",
        json={"key": ["04910766"], "changes": {"tokef_dt": "2030-01-01"}},
    )
    assert r.status_code == 200, r.text
    match = next(m for m in find(admin, "4910766")["matches"] if m["dataset_id"] == registry)
    assert field(match, "tokef_dt") == "2030-01-01"


def test_reading_access_is_enough_and_nobody_is_none(viewer, anon, registry):
    assert viewer.get("/api/catalog/lookup", params={"q": "4910766"}).status_code == 200
    assert anon.get("/api/catalog/lookup", params={"q": "4910766"}).status_code == 401


def test_the_lookup_is_rate_limited():
    """Cheap per call, but a loop of them walks the whole registry one plate at a time."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "app" / "routers" / "catalog.py").read_text(
        encoding="utf-8"
    )
    assert source.count("rate_limited(QUERY)") == 2


# ---- how many like it -------------------------------------------------------------------


@pytest.fixture(scope="module")
def fleet(admin) -> str:
    """Five vehicles: three Corollas, two with one engine and one with another, a Corolla
    from another make (the same trade name is not the same car), and a Kia with no
    engine code at all."""
    from conftest import wait_for_job

    body = (
        "mispar_rechev,tozeret_nm,kinuy_mishari,degem_manoa,shnat_yitzur\n"
        "11111111,טויוטה יפן,COROLLA,1ZR,2016\n"
        "22222222,טויוטה יפן,COROLLA,1ZR,2018\n"
        "33333333,טויוטה יפן,COROLLA,2ZR,2019\n"
        "44444444,טויוטה טורקיה,COROLLA,1ZR,2020\n"
        "55555555,קיה קוריאה,PICANTO,,2015\n"
    ).encode("utf-8")
    r = admin.post("/api/datasets/upload", files={"file": ("fleet.csv", body, "text/csv")})
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


def similar(client, dataset_id, q):
    r = client.get("/api/catalog/similar", params={"dataset_id": dataset_id, "q": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_cars_like_it_are_counted_by_model_then_engine(admin, fleet):
    out = similar(admin, fleet, "11111111")
    assert out["model"]["count"] == 3  # the Turkish-built Corolla is another make
    assert out["engine"]["count"] == 2
    assert [f["column"] for f in out["engine"]["filters"]] == ["tozeret_nm", "kinuy_mishari", "degem_manoa"]


def test_the_count_is_what_the_grid_then_shows(admin, fleet):
    """The card's number and the grid behind its link must agree, or the link lies."""
    out = similar(admin, fleet, "11111111")
    for part in ("model", "engine"):
        filters = [{"op": "eq", **f} for f in out[part]["filters"]]
        r = admin.post(f"/api/datasets/{fleet}/data", json={"filters": filters, "page_size": 10})
        assert r.status_code == 200, r.text
        assert r.json()["total_rows"] == out[part]["count"], part


def test_no_engine_code_means_no_engine_count(admin, fleet):
    out = similar(admin, fleet, "55555555")
    assert out["model"]["count"] == 1
    assert out["engine"] is None


def test_an_unknown_vehicle_or_dataset(admin, viewer, anon, fleet):
    assert similar(admin, fleet, "99999999") == {"model": None, "engine": None}
    assert similar(viewer, fleet, "11111111")["model"]["count"] == 3
    r = admin.get("/api/catalog/similar", params={"dataset_id": "nope", "q": "11111111"})
    assert r.status_code == 404 and r.json()["code"] == "dataset_not_found"
    r = anon.get("/api/catalog/similar", params={"dataset_id": fleet, "q": "11111111"})
    assert r.status_code == 401
