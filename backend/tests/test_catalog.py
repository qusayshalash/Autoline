"""The vehicle catalog: one car, by plate or chassis number, at /catalog.

Two halves. The lookup has to accept a number the way people write it - the registry stores
every plate zero-padded to eight characters, and 45% of real plates start with that zero -
and find it in whichever dataset holds it. The photo has to be a photo of the right model or
no photo at all: a confident picture of the wrong car under a caption naming this one is
worse than an empty frame.

The photo tests never touch the network. Wikipedia is replaced by an httpx MockTransport
answering the way the real search did when it was checked by hand.
"""

import httpx
import pytest
from app.config import settings
from app.services import vehicle_lookup, vehicle_photo


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
    assert anon.get("/api/catalog/photo", params={"make": "Kia", "model": "Picanto"}).status_code == 401


def test_the_lookup_is_rate_limited():
    """Cheap per call, but a loop of them walks the whole registry one plate at a time."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "app" / "routers" / "catalog.py").read_text(
        encoding="utf-8"
    )
    assert source.count("rate_limited(QUERY)") == 2


# ---- the photo ----------------------------------------------------------------------------


def wikipedia(pages):
    """A stand-in for the search endpoint, answering with `pages` and counting calls."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("q"))
        return httpx.Response(200, json={"pages": pages})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


THUMB = "//upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Kia_Picanto.jpg/60px-Kia_Picanto.jpg"


@pytest.fixture(autouse=True)
def fresh_photo_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "catalog_photos", True)
    vehicle_photo.clear()
    yield
    vehicle_photo.clear()


def test_the_photo_is_the_model_s_lead_image_made_larger():
    client, _ = wikipedia([{"title": "Kia Picanto", "thumbnail": {"url": THUMB}}])
    out = vehicle_photo.find("Kia", "PICANTO", client=client)
    assert out["url"] == THUMB.replace("//", "https://", 1).replace("/60px-", "/500px-")
    assert out["page"] == "https://en.wikipedia.org/wiki/Kia_Picanto"


def test_a_page_about_something_else_is_not_shown_as_the_car():
    """The search always returns something. "Kia Slovakia PICANTO" returned a list of
    Kia's factories when tried for real; an unknown model would return whatever ranked
    first. A wrong photo under a caption naming this model is worse than none."""
    for title in ("List of Kia design and manufacturing facilities", "Picanto (disambiguation)", "Toyota Corolla"):
        vehicle_photo.clear()
        client, _ = wikipedia([{"title": title, "thumbnail": {"url": THUMB}}])
        assert vehicle_photo.find("Kia", "PICANTO", client=client)["url"] is None, title


def test_an_accented_title_still_matches_the_make():
    """Škoda is written Skoda in the dictionary and Škoda on Wikipedia."""
    client, _ = wikipedia([{"title": "Škoda Octavia", "thumbnail": {"url": THUMB}}])
    assert vehicle_photo.find("Skoda", "OCTAVIA", client=client)["url"]


def test_only_wikimedia_images_are_passed_on():
    """Whatever the search returns is not trusted to be an image host."""
    client, _ = wikipedia([{"title": "Kia Picanto", "thumbnail": {"url": "https://evil.example/x.jpg"}}])
    assert vehicle_photo.find("Kia", "PICANTO", client=client)["url"] is None


def test_a_model_is_looked_up_once():
    client, calls = wikipedia([{"title": "Kia Picanto", "thumbnail": {"url": THUMB}}])
    for _ in range(3):
        vehicle_photo.find("Kia", "PICANTO", client=client)
    vehicle_photo.find("kia", "picanto", client=client)  # same model, other case
    assert calls == ["Kia PICANTO"]


def test_a_network_failure_is_not_remembered_as_no_photo():
    def broken(request):
        raise httpx.ConnectError("offline")

    client = httpx.Client(transport=httpx.MockTransport(broken))
    assert vehicle_photo.find("Kia", "PICANTO", client=client)["url"] is None
    good, calls = wikipedia([{"title": "Kia Picanto", "thumbnail": {"url": THUMB}}])
    assert vehicle_photo.find("Kia", "PICANTO", client=good)["url"], "the failure was cached"


def test_it_can_be_switched_off(monkeypatch):
    """For an installation with no internet: no call is made at all."""
    monkeypatch.setattr(settings, "catalog_photos", False)
    client, calls = wikipedia([{"title": "Kia Picanto", "thumbnail": {"url": THUMB}}])
    assert vehicle_photo.find("Kia", "PICANTO", client=client)["url"] is None
    assert calls == []


# ---- the screen half --------------------------------------------------------------------


def test_the_make_is_sent_without_its_country():
    """The registry writes "קיה סלובקיה"; the photo search needs "Kia"."""
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
    page = (src / "pages" / "CatalogPage.tsx").read_text(encoding="utf-8")
    assert 'makeName(make, "en")' in page
    dictionary = (src / "data" / "valueDictionary.ts").read_text(encoding="utf-8")
    assert "export function makeName(" in dictionary
    assert "...COUNTRIES," in dictionary


def test_the_photo_is_captioned_as_the_model_not_the_car():
    import io
    import json
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
    for lang in ("ar", "en", "he"):
        caption = json.load(io.open(src / "i18n" / f"{lang}.json", encoding="utf-8"))["catalog"]["photo_caption"]
        assert caption, lang
    page = (src / "pages" / "CatalogPage.tsx").read_text(encoding="utf-8")
    assert 't("catalog.photo_caption")' in page


# Captured from the real search on 2026-10-03, not written from memory. The first version
# of the host check accepted only upload.wikimedia.org; every real thumbnail comes from
# thumb.wikimedia.org with tracking parameters appended, so every photo was refused while
# the test above - mocked with the assumed host - passed.
REAL_THUMB = (
    "//thumb.wikimedia.org/wikipedia/commons/thumb/f/fe/"
    "Toyota_Corolla_Hybrid_%28E210%29_IMG_4338.jpg/60px-Toyota_Corolla_Hybrid_%28E210%29_IMG_4338.jpg"
    "?utm_source=en.wikipedia.org&utm_campaign=rest&utm_content=thumbnail"
)


def test_the_thumbnail_host_the_search_really_uses_is_accepted():
    client, _ = wikipedia([{"title": "Toyota Corolla", "thumbnail": {"url": REAL_THUMB}}])
    url = vehicle_photo.find("Toyota", "COROLLA", client=client)["url"]
    assert url == (
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fe/"
        "Toyota_Corolla_Hybrid_%28E210%29_IMG_4338.jpg/500px-Toyota_Corolla_Hybrid_%28E210%29_IMG_4338.jpg"
    )


def test_tracking_parameters_are_not_passed_on():
    client, _ = wikipedia([{"title": "Toyota Corolla", "thumbnail": {"url": REAL_THUMB}}])
    assert "utm_" not in vehicle_photo.find("Toyota", "COROLLA", client=client)["url"]


@pytest.mark.parametrize(
    "lookalike",
    [
        "//thumb.wikimedia.org.evil.example/x/60px-a.jpg",   # a suffix is not the host
        "//evil.example/thumb.wikimedia.org/60px-a.jpg",     # nor is a path
        "http://thumb.wikimedia.org/x/60px-a.jpg",           # nor plain http
    ],
)
def test_a_lookalike_host_is_refused(lookalike):
    client, _ = wikipedia([{"title": "Kia Picanto", "thumbnail": {"url": lookalike}}])
    assert vehicle_photo.find("Kia", "PICANTO", client=client)["url"] is None



def test_the_width_asked_for_is_one_wikimedia_renders():
    """Wikimedia renders only standard thumbnail steps. 640 is not one: it answered HTTP
    400, and every photo was a broken image while the URL looked perfectly well formed."""
    assert vehicle_photo.WIDTH in {120, 250, 330, 500, 960, 1280}



def test_a_saved_photo_at_another_width_is_not_served(monkeypatch, tmp_path):
    """Saved hits outlive restarts. When the width changed, the old addresses - which
    Wikimedia refuses - would otherwise have been served from disk indefinitely."""
    import json

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    (tmp_path / "photo_cache.json").write_text(
        json.dumps(
            {
                "kia|picanto": {"url": "https://thumb.wikimedia.org/a/640px-old.jpg", "title": "Kia Picanto"},
                "toyota|corolla": {"url": f"https://thumb.wikimedia.org/a/{vehicle_photo.WIDTH}px-ok.jpg", "title": "Toyota Corolla"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(vehicle_photo, "_loaded", False)
    vehicle_photo._cache.clear()
    client, calls = wikipedia([{"title": "Kia Picanto", "thumbnail": {"url": THUMB}}])
    vehicle_photo.find("Toyota", "COROLLA", client=client)
    vehicle_photo.find("Kia", "PICANTO", client=client)
    assert calls == ["Kia PICANTO"], "the stale 640px entry was served instead of looked up again"
