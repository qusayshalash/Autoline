"""What a request has to get past before any endpoint sees it.

Three gates, as plain ASGI rather than `@app.middleware("http")`, for two reasons found the
hard way.

**The order was wrong, and nothing said so.** Starlette's `add_middleware` inserts at the
front of the list, so the *last* one added ends up *outermost* - the opposite of how the
code reads. CORS had been added first, which made it the innermost layer, and every
refusal these gates produced - the restore's 503, the flood gate's 429 - went out without
Access-Control-Allow-Origin. A browser on another origin cannot read such a response at
all: the restore screen never saw the stage it was built to show, and somebody being
rate limited saw a network error instead of "slow down". It was invisible to the tests
because the test client sends no Origin. `install` below adds them in the one order that
works and says why; tests/test_gates.py checks every refusal carries the header.

**Counting a body means wrapping `receive`**, which the decorator form cannot do. A
declared Content-Length can be absent - chunked uploads never send one - and any client
can lie in it, so the size is counted as the bytes arrive, not believed from a header.
"""

import os
import re
import shutil
import tempfile
from typing import Optional

from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.errors import ApiError
from app.services import rate_limit
from app.services import restore as restore_service

# A JSON body in this app is a filter list, a search, a cleaning config, a pivot. The
# largest a person can build through the screen is a value picker with every one of its
# 500 values ticked, which is tens of kilobytes. A megabyte is generous by a factor of
# twenty and still far below the point where reading it is the attack.
MAX_BODY_BYTES = 1024 * 1024

# The two endpoints that legitimately receive a file. Their limit is not a size - the
# registry export this is built against is 867 MB and a byte ceiling would reject it with
# the runaway uploads - but the room on the disk that has to hold it.
_UPLOAD_PATHS = re.compile(r"^/api/datasets/(upload|[0-9a-f]{32}/append)$")

# How often an upload in progress re-checks the disk. Every chunk would be a system call
# per 64 KB; this is one per 64 MB, which on an 867 MB file is fourteen checks.
_RECHECK_EVERY = 64 * 1024 * 1024


def _json(status: int, code: str, detail: str, headers: Optional[dict] = None) -> tuple:
    import json

    body = json.dumps({"detail": detail, "code": code}).encode("utf-8")
    raw_headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), str(v).encode()))
    return (
        {"type": "http.response.start", "status": status, "headers": raw_headers},
        {"type": "http.response.body", "body": body},
    )


async def _refuse(send: Send, status: int, code: str, detail: str, headers: Optional[dict] = None) -> None:
    start, body = _json(status, code, detail, headers)
    await send(start)
    await send(body)


def _header(scope: Scope, name: bytes) -> Optional[str]:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return None


# ---- the maintenance gate -------------------------------------------------------------


class MaintenanceGate:
    """Stops answering while a restore is swapping the files underneath us.

    A request arriving in that window would reopen the catalog on a file mid-rename, and
    on Windows its handle would make the rename fail - so the failure is not a stale read,
    it is a half-finished restore. The refusal carries the stage, which is how the screen
    watching the restore follows it without an endpoint that reads the database being
    replaced.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/api/") and restore_service.is_active():
            import json

            body = json.dumps(
                {
                    "detail": "A restore is in progress",
                    "code": "maintenance",
                    "stage": restore_service.status()["stage"],
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"retry-after", b"5"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


# ---- the flood gate -------------------------------------------------------------------


class FloodGate:
    """A ceiling on how fast one address may ask for anything at all.

    In front of everything and in memory, because of where the cost is: the guard against
    password guessing writes a row for every failed attempt, and the catalog is one DuckDB
    file behind one lock. A few hundred concurrent wrong passwords put every other catalog
    read in a queue. This is checked before anything touches the database. Health is
    exempt - whatever is watching the process must not be told to go away.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["path"].startswith("/api/")
            and scope["path"] != "/api/health"
        ):
            client = scope.get("client")
            key = rate_limit.key_for(None, client[0] if client else None)
            wait = rate_limit.check(rate_limit.GLOBAL, key)
            if wait > 0:
                await _refuse(
                    send,
                    429,
                    "too_many_requests",
                    "Too many requests - slow down and try again shortly",
                    {"Retry-After": max(1, int(wait + 0.999))},
                )
                return
        await self.app(scope, receive, send)


# ---- the body limit -------------------------------------------------------------------


def upload_room() -> int:
    """How many bytes an upload may be, given the disks it has to land on.

    Two disks, not one, and this is the part that was not obvious. The framework parses
    a multipart upload *before* the endpoint runs, spooling the whole file into the
    system temp directory; only then does the endpoint copy it into the data directory.
    Measured: by the time the handler's first line runs, all of a 5 MB test file is
    already in %TEMP%. So the existing guard - which checks free space as it copies into
    the data directory - protected the second copy and never the first. A 50 GB upload
    would have filled the temp drive before the guard ran at all. On a Linux host where
    /tmp is a RAM-backed tmpfs it would have filled memory instead.

    When both directories are on one volume the file is there twice for a moment, so the
    room is halved.
    """
    temp = tempfile.gettempdir()
    data = settings.data_dir
    try:
        free_temp = shutil.disk_usage(temp).free
        free_data = shutil.disk_usage(data).free
        same_volume = os.stat(temp).st_dev == os.stat(data).st_dev
    except OSError:
        return 0
    margin = settings.min_free_disk_bytes
    if same_volume:
        return max(0, (min(free_temp, free_data) - margin) // 2)
    return max(0, min(free_temp, free_data) - margin)


class BodyLimit:
    """Refuses a request whose body is bigger than the thing it is for.

    Two limits. An ordinary request is capped at a megabyte. An upload is capped at what
    the disks can hold, because the file-size decision was already made - the 867 MB
    registry must fit - and what is left to protect is the disk.

    Checked twice. The declared Content-Length is checked before a byte is read, which
    turns away the honest oversized request immediately. The bytes are then counted as
    they arrive, because a chunked request declares nothing and any client can declare a
    lie. The counted refusal is raised as an ApiError from inside `receive`, which is the
    one exception type the framework's body parser passes through untouched - anything
    else it rewrites as a 400 about malformed JSON, which would be true of nothing.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        upload = scope.get("method") == "POST" and bool(_UPLOAD_PATHS.match(scope["path"]))
        limit = upload_room() if upload else MAX_BODY_BYTES

        declared = _header(scope, b"content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                # the server's HTTP parser rejects this before it reaches the app; if one
                # ever gets through, counting the bytes below still bounds it
                size = 0
            if size > limit:
                if upload:
                    await _refuse(send, 413, "upload_no_room", "Not enough free disk space for this upload")
                else:
                    await _refuse(send, 413, "request_too_large", "Request body is too large")
                return

        received = 0
        next_check = _RECHECK_EVERY

        async def counted() -> Message:
            nonlocal received, next_check
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if not upload and received > MAX_BODY_BYTES:
                    raise ApiError(413, "request_too_large", "Request body is too large")
                if upload and received >= next_check:
                    next_check += _RECHECK_EVERY
                    # the room left now, not at the start: this is the disk every other
                    # dataset lives on, and what is free can shrink for reasons that have
                    # nothing to do with this upload
                    if upload_room() <= 0:
                        raise ApiError(
                            413, "upload_no_room", "Not enough free disk space for this upload"
                        )
            return message

        await self.app(scope, counted, send)


# ---- putting them in order ------------------------------------------------------------


def install(app, allowed_origins: list[str]) -> None:
    """Adds the gates and CORS in the only order that works.

    `add_middleware` inserts at the front, so the last added is the outermost. Reading
    top to bottom below is therefore reading from the inside out, which is backwards from
    how anyone reads it - hence the comment beside each line.
    """
    app.add_middleware(BodyLimit)        # innermost: only sees what survived the rest
    app.add_middleware(FloodGate)        # a dictionary lookup, before any byte is counted
    app.add_middleware(MaintenanceGate)  # nothing runs during a restore, not even counting
    app.add_middleware(                  # outermost: so every refusal above is readable
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # A cross-origin response hides every header from JavaScript unless it is named
        # here. The login screen reads Retry-After to say how long somebody is locked out,
        # and a rate-limited screen reads it to say how long to wait.
        expose_headers=["Retry-After"],
    )
