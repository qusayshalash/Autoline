"""A real photo of one vehicle, uploaded at /catalog.

An upload endpoint is an invitation to send anything, so most of these are the things that
should not get through: a text file with an image's name, garbage behind an image's first
bytes, an image that declares an enormous canvas to exhaust memory when decoded. And the
one that would get through unnoticed if nothing were done about it: a phone photo carries
the GPS position it was taken at, and a photo of a car in a driveway records where somebody
lives. Every one of these is answered by the same step - nothing is stored as it arrived;
it is decoded and written out again as a fresh JPEG - and each is checked here by reading
back what the server actually serves.
"""

import io
import struct
import zlib

import pytest
from PIL import Image

from app.services import vehicle_photos

PLATE = "04910766"


def image_bytes(fmt="JPEG", size=(320, 200), mode="RGB", color=(30, 120, 200), exif=None) -> bytes:
    img = Image.new(mode, size, color if mode != "RGBA" else (*color, 0))
    out = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    img.save(out, fmt, **kwargs)
    return out.getvalue()


def with_gps() -> bytes:
    """A JPEG carrying a GPS position and a camera make, as a phone writes them."""
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"                       # Make
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (31.0, 46.0, 30.0)                       # Jerusalem, roughly
    gps[3] = "E"
    gps[4] = (35.0, 13.0, 0.0)
    return image_bytes(exif=exif)


def sideways() -> bytes:
    """Landscape pixels with Orientation=6: a phone held upright, saved sideways."""
    exif = Image.Exif()
    exif[0x0112] = 6
    return image_bytes(size=(400, 200), exif=exif)


def bomb() -> bytes:
    """A PNG declaring 30,000 x 30,000 pixels in a file of a few dozen bytes."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", 30000, 30000, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def clean():
    vehicle_photos.clear_all()
    yield
    vehicle_photos.clear_all()


def upload(client, data: bytes, name="car.jpg", plate=PLATE, ctype="image/jpeg"):
    return client.post(f"/api/catalog/vehicles/{plate}/photo", files={"file": (name, data, ctype)})


def served(client, plate=PLATE) -> Image.Image:
    r = client.get(f"/api/catalog/vehicles/{plate}/photo")
    assert r.status_code == 200, r.text
    return Image.open(io.BytesIO(r.content))


# ---- what gets through, and what it becomes ----------------------------------------------


def test_a_photo_is_stored_and_served_as_a_jpeg(admin):
    r = upload(admin, image_bytes())
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["plate"] == PLATE and info["width"] == 320 and info["height"] == 200
    assert info["uploaded_by"] == "test_admin"

    got = admin.get(f"/api/catalog/vehicles/{PLATE}/photo")
    assert got.headers["content-type"] == "image/jpeg"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.content[:3] == b"\xff\xd8\xff"


def test_the_gps_position_does_not_survive(admin):
    """The privacy half. A photo of a car in a driveway records where somebody lives."""
    original = Image.open(io.BytesIO(with_gps()))
    assert 0x8825 in original.getexif(), "the test photo has no GPS to remove"

    assert upload(admin, with_gps()).status_code == 200
    exif = served(admin).getexif()
    assert 0x8825 not in exif, "the GPS position was kept"
    assert 0x010F not in exif, "camera metadata was kept"
    assert len(exif) == 0


def test_a_sideways_phone_photo_is_upright(admin):
    """Orientation is applied before the metadata saying it is dropped - the other order
    would store a car lying on its side, permanently."""
    assert upload(admin, sideways()).status_code == 200
    assert served(admin).size == (200, 400)


@pytest.mark.parametrize("fmt,mode,ctype", [("PNG", "RGBA", "image/png"), ("WEBP", "RGB", "image/webp")])
def test_png_and_webp_are_accepted_and_become_jpeg(admin, fmt, mode, ctype):
    r = upload(admin, image_bytes(fmt=fmt, mode=mode), name=f"car.{fmt.lower()}", ctype=ctype)
    assert r.status_code == 200, r.text
    img = served(admin)
    assert img.format == "JPEG" and img.mode == "RGB"


def test_a_huge_photo_is_kept_at_a_sensible_size(admin):
    assert upload(admin, image_bytes(size=(4000, 3000))).status_code == 200
    assert max(served(admin).size) == vehicle_photos.MAX_EDGE


# ---- what does not get through ---------------------------------------------------------


@pytest.mark.parametrize(
    "data,name",
    [
        (b"just some text, renamed", "car.jpg"),
        (b"\xff\xd8\xff" + b"\x00" * 200, "car.jpg"),                     # a JPEG's first bytes, then nothing
        (b"<script>alert(1)</script>", "car.png"),
        (b"%PDF-1.7\n" + b"x" * 100, "car.jpg"),
    ],
)
def test_what_is_not_an_image_is_refused(admin, data, name):
    r = upload(admin, data, name=name)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "photo_not_an_image"
    assert vehicle_photos.get(PLATE) is None


def test_an_image_declaring_an_enormous_canvas_is_refused_before_decoding(admin):
    """A few dozen bytes claiming 900 million pixels: decoding it is the attack."""
    data = bomb()
    assert len(data) < 200
    r = upload(admin, data, name="car.png", ctype="image/png")
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "photo_too_many_pixels"


def test_the_type_the_browser_claims_is_not_believed(admin):
    """Content-Type is whatever the sender wrote. The first bytes decide."""
    r = upload(admin, b"not an image at all", ctype="image/jpeg")
    assert r.json()["code"] == "photo_not_an_image"


@pytest.mark.parametrize("plate", ["123", "1234567a", "123456789", "0491076"])
def test_only_a_plate_is_a_plate(admin, plate):
    r = upload(admin, image_bytes(), plate=plate)
    assert r.status_code in (400, 404), r.text
    if r.status_code == 400:
        assert r.json()["code"] == "photo_bad_plate"


def test_a_path_cannot_be_walked_out_of(admin):
    for plate in ("..%2F..%2Fsecret_key", "%2E%2E", "../04910766"):
        r = admin.get(f"/api/catalog/vehicles/{plate}/photo")
        assert r.status_code in (400, 404), (plate, r.status_code)


# ---- size ------------------------------------------------------------------------------


def test_a_phone_sized_photo_is_not_held_to_the_one_megabyte_limit(admin):
    """Every other request is capped at 1 MB, which would refuse every real photo."""
    import os

    noisy = Image.frombytes("RGB", (1600, 1200), os.urandom(1600 * 1200 * 3))
    out = io.BytesIO()
    noisy.save(out, "JPEG", quality=98)
    data = out.getvalue()
    assert len(data) > 1024 * 1024, len(data)
    assert upload(admin, data).status_code == 200


def test_more_than_the_photo_limit_is_refused(admin):
    from app import gates

    r = upload(admin, b"\xff\xd8\xff" + b"0" * (gates.MAX_PHOTO_BYTES + 10))
    assert r.status_code == 413
    assert r.json()["code"] == "photo_too_large"


# ---- replacing, removing, finding ------------------------------------------------------


def test_uploading_again_replaces_and_gets_a_new_address(admin):
    first = upload(admin, image_bytes(color=(200, 0, 0))).json()
    second = upload(admin, image_bytes(color=(0, 200, 0))).json()
    assert first["photo_id"] != second["photo_id"]
    files = list((vehicle_photos.root() / PLATE).glob("*.jpg"))
    assert [f.stem for f in files] == [second["photo_id"]], "the replaced file was left behind"


def test_a_removed_photo_is_gone(admin):
    upload(admin, image_bytes())
    assert admin.delete(f"/api/catalog/vehicles/{PLATE}/photo").status_code == 200
    assert admin.get(f"/api/catalog/vehicles/{PLATE}/photo").status_code == 404
    assert admin.delete(f"/api/catalog/vehicles/{PLATE}/photo").status_code == 404
    assert not (vehicle_photos.root() / PLATE).exists()


def test_the_lookup_carries_the_photo(admin):
    """The photo is per plate, so it reaches every row found for that plate, whichever
    dataset it came from."""
    from conftest import wait_for_job

    body = "mispar_rechev,kinuy_mishari\n04910766,PICANTO\n".encode()
    ds = admin.post("/api/datasets/upload", files={"file": ("p.csv", body, "text/csv")}).json()["dataset_id"]
    r = admin.post(f"/api/datasets/{ds}/import", json={"encoding": "utf-8", "delimiter": ",", "has_header": True})
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    try:
        before = admin.get("/api/catalog/lookup", params={"q": "4910766"}).json()
        assert all(m["photo"] is None for m in before["matches"])
        info = upload(admin, image_bytes()).json()
        after = admin.get("/api/catalog/lookup", params={"q": "4910766"}).json()
        mine = next(m for m in after["matches"] if m["dataset_id"] == ds)
        assert mine["photo"]["photo_id"] == info["photo_id"]
    finally:
        admin.delete(f"/api/datasets/{ds}")


# ---- who may ---------------------------------------------------------------------------


def test_who_may_add_and_who_may_look(admin, editor, viewer, anon):
    assert upload(viewer, image_bytes()).status_code == 403
    assert upload(editor, image_bytes()).status_code == 200
    assert viewer.get(f"/api/catalog/vehicles/{PLATE}/photo").status_code == 200
    assert viewer.delete(f"/api/catalog/vehicles/{PLATE}/photo").status_code == 403
    assert anon.get(f"/api/catalog/vehicles/{PLATE}/photo").status_code == 401


def test_adding_and_removing_are_in_the_activity_log(admin):
    upload(admin, image_bytes())
    upload(admin, image_bytes())
    admin.delete(f"/api/catalog/vehicles/{PLATE}/photo")
    actions = [i["action"] for i in admin.get("/api/admin/activity", params={"limit": 10}).json()["items"]]
    assert actions[:3] == ["vehicle.photo_removed", "vehicle.photo_replaced", "vehicle.photo_added"]


# ---- backups -----------------------------------------------------------------------------


def test_a_backup_contains_the_photos_whether_or_not_originals_are_asked_for(admin):
    """A photo taken at the counter exists nowhere else. It cannot hide behind the
    'include originals' checkbox the way a re-uploadable file can."""
    from app.services import backup

    upload(admin, image_bytes())
    manifest = backup.run(include_originals=False)
    try:
        assert manifest["verified"], manifest["errors"]
        photos = [i for i in manifest["items"] if i["kind"] == "photo"]
        assert len(photos) == 1
        stored = vehicle_photos.file_for(PLATE).read_bytes()
        copied = (backup.backups_root() / manifest["name"] / photos[0]["file"]).read_bytes()
        assert copied == stored
    finally:
        backup.delete(manifest["name"])


def test_a_restore_brings_a_deleted_photo_back(admin, editor, viewer, dataset):
    """Every session-scoped account and dataset is requested so the backup taken here is
    the whole world - restoring it changes nothing but the photo. See test_restore for why
    that matters."""
    from app.services import backup, restore

    info = upload(admin, image_bytes()).json()
    manifest = backup.run()
    try:
        admin.delete(f"/api/catalog/vehicles/{PLATE}/photo")
        assert admin.get(f"/api/catalog/vehicles/{PLATE}/photo").status_code == 404

        result = restore.run(manifest["name"], actor_note="test")
        assert result["ok"], result

        assert vehicle_photos.get(PLATE)["photo_id"] == info["photo_id"]
        assert admin.get(f"/api/catalog/vehicles/{PLATE}/photo").status_code == 200
    finally:
        backup.delete(manifest["name"])
        for kept in restore.kept_states():
            restore.delete_kept(kept["name"])


# ---- the screen half ---------------------------------------------------------------------


def test_the_real_photo_is_preferred_and_labelled():
    from pathlib import Path

    page = (Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "pages" / "CatalogPage.tsx").read_text(
        encoding="utf-8"
    )
    assert "const url = real ?? representative;" in page, "the real photo must win over the model's"
    assert "enabled: !!make && !photo" in page, "the model photo is fetched only when it will be shown"
    assert 't("catalog.photo_real"' in page
    assert 'can("datasets.upload")' in page
