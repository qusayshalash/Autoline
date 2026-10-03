"""A real photo of one vehicle, uploaded by a person, shown in the catalog.

The catalog's other picture is a photo of the *model*, found on Wikipedia and captioned as
such. This is the one that is actually of the car - taken at the counter, or sent in - and
the screen prefers it whenever there is one.

**Nothing is stored as it arrived.** Every upload is opened as an image and written out
again as a new JPEG. That one step does four jobs:

  * It proves the file is an image. A text file renamed .jpg, a script with an image's
    first few bytes in front of it, an image that claims to be 50,000 pixels square to
    exhaust memory on decoding - none of them survive being decoded and re-encoded.
  * It removes the metadata. A phone photo carries the GPS position it was taken at, and
    a photo of a car taken in a driveway records where somebody lives. EXIF is not copied
    across; neither is anything else.
  * It applies the camera's orientation first, so a photo held sideways is upright.
  * It bounds what is kept: the long edge is brought down to MAX_EDGE, so an upload of
    12 MB becomes a few hundred KB. The upload limit (gates.MAX_PHOTO_BYTES) bounds what
    is accepted; this bounds what is stored.

One photo per plate. Uploading again replaces it, and the new photo gets a new id - which
is also its file name and part of its address - so no browser holding the old one in its
cache will keep showing it.

The plate is the registry's own form, eight digits, and is validated as exactly that before
it is used anywhere near a path.
"""

import io
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from app.config import settings
from app.db import catalog
from app.services import clocks

PHOTOS_DIRNAME = "vehicle_photos"

# Long edge kept. Enough to see a dent on a card a few hundred pixels wide, opened full
# screen on a laptop; not enough to be a storage problem across a fleet.
MAX_EDGE = 2000
JPEG_QUALITY = 85

# Decoding is where an image attacks: a small file can declare an enormous canvas. This
# is far above any camera (a 50 MP phone is 50,000,000) and far below what would exhaust
# a server's memory.
MAX_PIXELS = 80_000_000

# What is accepted, checked from the file's first bytes - never from its name or from the
# type the browser claims.
_SIGNATURES = (
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
)
_PLATE = re.compile(r"^[0-9]{8}$")


class PhotoProblem(Exception):
    """A photo refused for a reason the person uploading it should read."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def root() -> Path:
    return settings.data_dir / PHOTOS_DIRNAME


def valid_plate(plate: str) -> bool:
    return bool(_PLATE.match(plate or ""))


def _kind(data: bytes) -> Optional[str]:
    for magic, kind in _SIGNATURES:
        if data.startswith(magic):
            return kind
    # WebP is a RIFF container: the format name sits at offset 8
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _reencode(data: bytes) -> tuple[bytes, int, int]:
    """The upload as a fresh JPEG with no metadata, upright and bounded. Raises
    PhotoProblem for anything that is not a decodable image of an accepted kind."""
    kind = _kind(data)
    if kind is None:
        raise PhotoProblem("photo_not_an_image", "The file is not a JPEG, PNG or WebP image")

    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != kind:
                # the first bytes said one thing and the decoder found another
                raise PhotoProblem("photo_not_an_image", "The file is not a JPEG, PNG or WebP image")
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > MAX_PIXELS:
                raise PhotoProblem("photo_too_many_pixels", "The image is too large to process")
            img.load()
            upright = ImageOps.exif_transpose(img)
            if upright.mode in ("RGBA", "LA", "P"):
                # a transparent PNG flattened onto white, as it would print
                rgba = upright.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                upright = flat
            elif upright.mode != "RGB":
                upright = upright.convert("RGB")
            upright.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            # no exif=, no icc_profile=, no info carried across: what is written is pixels
            upright.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            return out.getvalue(), upright.width, upright.height
    except PhotoProblem:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise PhotoProblem("photo_too_many_pixels", "The image is too large to process") from None
    except Exception as exc:  # noqa: BLE001 - any decoder failure means "not an image"
        raise PhotoProblem("photo_not_an_image", "The file is not a JPEG, PNG or WebP image") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous


def _path(plate: str, photo_id: str) -> Path:
    return root() / plate / f"{photo_id}.jpg"


def get(plate: str) -> Optional[dict]:
    if not valid_plate(plate):
        return None
    conn = catalog.get_connection()
    with catalog.db_lock:
        row = conn.execute(
            "SELECT plate, photo_id, bytes, width, height, uploaded_by, uploaded_at"
            " FROM vehicle_photos WHERE plate = ?",
            [plate],
        ).fetchone()
    if row is None:
        return None
    keys = ("plate", "photo_id", "bytes", "width", "height", "uploaded_by", "uploaded_at")
    out = dict(zip(keys, row))
    out["uploaded_at"] = clocks.iso(out["uploaded_at"])
    return out


def get_many(plates: list[str]) -> dict[str, dict]:
    return {p: info for p in set(plates) if (info := get(p))}


def file_for(plate: str) -> Optional[Path]:
    info = get(plate)
    if not info:
        return None
    path = _path(plate, info["photo_id"])
    return path if path.is_file() else None


def save(plate: str, data: bytes, actor_username: str) -> dict:
    """Stores a new photo for this plate, replacing any earlier one."""
    if not valid_plate(plate):
        raise PhotoProblem("photo_bad_plate", "Not a plate number")
    jpeg, width, height = _reencode(data)

    photo_id = uuid.uuid4().hex
    target = _path(plate, photo_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    # written beside the target and renamed into place, so a reader never meets half a file
    partial = target.with_suffix(".part")
    partial.write_bytes(jpeg)
    partial.replace(target)

    previous = get(plate)
    conn = catalog.get_connection()
    with catalog.db_lock:
        conn.execute(
            """
            INSERT INTO vehicle_photos (plate, photo_id, bytes, width, height, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (plate) DO UPDATE SET
                photo_id = excluded.photo_id, bytes = excluded.bytes,
                width = excluded.width, height = excluded.height,
                uploaded_by = excluded.uploaded_by, uploaded_at = excluded.uploaded_at
            """,
            [plate, photo_id, len(jpeg), width, height, actor_username, clocks.now()],
        )
    # the old file goes only once the new one is recorded: a failure in between leaves an
    # extra file, never a photo with nothing behind it
    if previous:
        _path(plate, previous["photo_id"]).unlink(missing_ok=True)
    return get(plate) or {}


def remove(plate: str) -> bool:
    info = get(plate)
    if not info:
        return False
    conn = catalog.get_connection()
    with catalog.db_lock:
        conn.execute("DELETE FROM vehicle_photos WHERE plate = ?", [plate])
    _path(plate, info["photo_id"]).unlink(missing_ok=True)
    folder = root() / plate
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    return True


def total_bytes() -> int:
    base = root()
    if not base.exists():
        return 0
    return sum(p.stat().st_size for p in base.rglob("*.jpg") if p.is_file())


def clear_all() -> None:
    """For tests."""
    conn = catalog.get_connection()
    with catalog.db_lock:
        conn.execute("DELETE FROM vehicle_photos")
    shutil.rmtree(root(), ignore_errors=True)
