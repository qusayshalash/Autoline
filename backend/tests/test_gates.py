"""What a request has to get past before any endpoint sees it.

Two things are pinned here. The body limit, which is new. And the order of the layers,
which was wrong: Starlette's `add_middleware` puts the last one added outermost, CORS had
been added first, and so the restore's 503 and the rate limiter's 429 went out without
Access-Control-Allow-Origin. A browser on another origin cannot read such a response at
all. The rest of the suite could not see it because the test client sends no Origin -
so every refusal here is requested *with* one.
"""

import pytest
from app import gates
from app.config import settings
from app.services import rate_limit, restore

ORIGIN = {"Origin": "http://localhost:5173"}


def readable_by_the_browser(r) -> bool:
    return r.headers.get("access-control-allow-origin") == ORIGIN["Origin"]


# ---- every refusal can be read by the screen -------------------------------------------


def test_an_ordinary_response_carries_cors(anon):
    """The baseline the others are compared against."""
    assert readable_by_the_browser(anon.get("/api/datasets", headers=ORIGIN))


def test_the_restore_refusal_can_be_read(admin):
    """The screen watching a restore learns the stage from this response and nothing
    else. Without the header it saw a network error and guessed."""
    restore.begin("probe")
    try:
        r = admin.get("/api/admin/restore/status", headers=ORIGIN)
        assert r.status_code == 503
        assert readable_by_the_browser(r), "the 503 cannot be read cross-origin"
        assert r.json()["stage"] == "checking"
    finally:
        restore._end(False, "probe")


def test_the_rate_limit_refusal_can_be_read(anon):
    """Somebody being rate limited should read "slow down", not "network error"."""
    rate_limit.clear()
    settings.rate_limit_enabled = True
    try:
        r = None
        for _ in range(int(rate_limit.GLOBAL.burst) + 20):
            r = anon.get("/api/datasets", headers=ORIGIN)
            if r.status_code == 429:
                break
        assert r is not None and r.status_code == 429
        assert readable_by_the_browser(r), "the 429 cannot be read cross-origin"
    finally:
        settings.rate_limit_enabled = False
        rate_limit.clear()


def test_the_size_refusal_can_be_read(admin, dataset):
    body = b'{"search": "' + b"x" * (gates.MAX_BODY_BYTES + 10) + b'"}'
    r = admin.post(
        f"/api/datasets/{dataset}/data",
        content=body,
        headers={**ORIGIN, "content-type": "application/json"},
    )
    assert r.status_code == 413
    assert readable_by_the_browser(r)


def test_cors_is_the_outermost_layer():
    """The rule itself, so a middleware added later in the wrong place fails here rather
    than in a browser."""
    from app.main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    assert names[0] == "CORSMiddleware", names


# ---- the body limit ---------------------------------------------------------------------


def test_an_oversized_body_is_refused_before_it_is_read(admin, dataset):
    """Declared honestly, refused immediately, with a code the screen can translate."""
    body = b'{"search": "' + b"x" * (gates.MAX_BODY_BYTES + 10) + b'"}'
    r = admin.post(
        f"/api/datasets/{dataset}/data",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json()["code"] == "request_too_large"


def test_a_body_that_declares_nothing_is_still_counted(admin, dataset):
    """Chunked requests send no Content-Length and any client can send a false one. The
    size has to be counted as it arrives, not believed from a header."""

    def chunks():
        yield b'{"search": "'
        for _ in range(20):
            yield b"x" * 65536
        yield b'"}'

    r = admin.post(
        f"/api/datasets/{dataset}/data",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413, r.text
    # the framework's JSON parser rewrites any exception it meets as a 400 about bad JSON;
    # this one has to come through as what it is
    assert r.json()["code"] == "request_too_large"


def test_an_ordinary_body_is_untouched(admin, dataset):
    """A value picker with every one of its 500 values ticked is the largest body the
    screen can build. It must be nowhere near the limit."""
    values = [f"VALUE_{i:05d}_SOMEWHAT_LONG_NAME" for i in range(500)]
    r = admin.post(
        f"/api/datasets/{dataset}/data",
        json={
            "page": 1,
            "page_size": 10,
            "filters": [{"column": "tozeret_nm", "op": "in", "values": values}],
        },
    )
    assert r.status_code == 200, r.text


def test_an_upload_is_not_held_to_the_json_limit(admin):
    """The registry this was built for is 867 MB. A byte ceiling on uploads would turn
    it away with the runaway ones."""
    body = b"plate,make\n" + b"".join(b"%d,KIA\n" % i for i in range(200_000))
    assert len(body) > gates.MAX_BODY_BYTES
    r = admin.post("/api/datasets/upload", files={"file": ("big.csv", body, "text/csv")})
    assert r.status_code == 200, r.text
    admin.delete(f"/api/datasets/{r.json()['dataset_id']}")


def test_an_upload_bigger_than_the_disk_is_refused_before_it_lands(admin, monkeypatch):
    """The finding behind the upload half. The framework spools a multipart file into
    the system temp directory before the endpoint runs, so the existing free-space guard
    - which checks as it copies into the data directory - never protected the first copy.
    This refuses by what the disks can hold, before a byte is spooled."""
    monkeypatch.setattr(gates, "upload_room", lambda: 1000)
    r = admin.post(
        "/api/datasets/upload", files={"file": ("big.csv", b"x" * 5000, "text/csv")}
    )
    assert r.status_code == 413
    assert r.json()["code"] == "upload_no_room"


def test_the_room_is_halved_when_both_copies_share_a_disk(monkeypatch):
    """Spooled to temp, then copied to the data directory: on one volume the file is
    there twice for a moment."""
    import os
    import shutil
    from collections import namedtuple

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: usage(0, 0, 10_000_000_000))
    monkeypatch.setattr(settings, "min_free_disk_bytes", 1_000_000_000)

    real_stat = os.stat

    class Same:
        st_dev = 1

    monkeypatch.setattr(os, "stat", lambda _p, *a, **k: Same())
    assert gates.upload_room() == 4_500_000_000

    devices = iter([1, 2])

    class Next:
        @property
        def st_dev(self):
            return next(devices)

    monkeypatch.setattr(os, "stat", lambda _p, *a, **k: Next())
    assert gates.upload_room() == 9_000_000_000
    monkeypatch.setattr(os, "stat", real_stat)
