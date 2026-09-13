import os
import threading
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import admin as admin_db
from app.db import timestamp_migration
from app.errors import ApiError
from app.routers import (
    admin,
    auth,
    cleaning,
    data,
    datasets,
    export,
    jobs,
    roles,
    statistics,
    users,
)
from app.services import backup as backup_service
from app.services import housekeeping
from app.services import storage
from app.services.security import bootstrap_admin

app = FastAPI(title="CSV Analyzer API", version="0.1.0")


@app.exception_handler(ApiError)
async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
    """Adds the code beside the sentence, without moving the sentence.

    `detail` stays a string holding exactly what it held before, so anything already
    reading it - including an interface that does not know about codes yet - is
    unaffected. `code` is the part the interface translates.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
        headers=exc.headers,
    )

# The dev server, plus wherever the app is actually served from once it is deployed.
# PUBLIC_ORIGIN has to appear here as well as driving the cookie's Secure flag: with
# allow_credentials the list cannot be "*", so an origin missing from it cannot reach
# the API at all - and a setting that switched on cookie security while making the API
# unreachable would be worse than no setting.
_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
if settings.public_origin:
    origin = settings.public_origin.strip().rstrip("/")
    if origin not in _ALLOWED_ORIGINS:
        _ALLOWED_ORIGINS.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # A cross-origin response hides every header from JavaScript unless it is named here.
    # The login screen reads Retry-After to tell somebody how long they are locked out;
    # without this it can only guess, and would report a minute for an hour-long wait.
    expose_headers=["Retry-After"],
)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_dirs()

    # Corrects timestamps written before the UTC rule was settled. Records that it has
    # run, so it cannot shift the same rows twice.
    #
    # It has to come before seed(), and the order is the whole of a bug this once had.
    # The migration assumes every row it finds was written by an older version, in local
    # wall-clock, and subtracts the offset. Run after seed() it found the built-in roles
    # seed() had just inserted - correct UTC, written seconds earlier - and moved them
    # three hours into the past. On a fresh install that was every role in the database;
    # on an upgrade it would be any role a later version had newly added. Going first, it
    # can only ever see rows that were already there, which is the only thing it is for.
    #
    # Nothing writes a timestamped row before this point: the schema is created empty,
    # and reaching for the connection here is what creates it.
    try:
        result = timestamp_migration.run(
            admin_db.get_connection(), admin_db.get_setting, admin_db.set_setting
        )
        if result.get("applied"):
            print(f"[startup] corrected {result['shifted_rows']:,} stored timestamps to UTC")
    except Exception as exc:  # noqa: BLE001 - never block startup over a migration
        print(f"[startup] timestamp migration failed: {exc}")

    # roles and permissions must exist before the first account is created, since the
    # bootstrap admin is given a role by slug
    admin_db.seed()

    bootstrap_admin()

    # Export retention, applied on every boot. Without this the exports folder only ever
    # grows - which is exactly how it reached 2.8 GB before the setting was honoured.
    try:
        swept = storage.sweep_expired_exports()
        if swept["removed_files"]:
            print(
                f"[startup] removed {swept['removed_files']} expired export(s), "
                f"{swept['freed_bytes']:,} bytes"
            )
    except Exception as exc:  # noqa: BLE001 - never block startup over housekeeping
        print(f"[startup] export sweep failed: {exc}")

    # The backup schedule is a floor, not a clock: it asks whether the newest verified
    # backup is older than the interval. A machine that was switched off does not miss
    # its window - it takes one as soon as it comes back, which is what somebody
    # returning after a week actually wants.
    _start_housekeeping()


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(admin.router)
app.include_router(datasets.router)
app.include_router(jobs.router)
app.include_router(cleaning.router)
app.include_router(data.router)
app.include_router(statistics.router)
app.include_router(export.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---- periodic housekeeping --------------------------------------------------

# How often the schedule is re-examined. Not how often a backup is taken - that is the
# configured interval. Checking is a directory listing, so it can be cheap and frequent
# without the check itself being the thing that costs anything.
_SCHEDULE_CHECK_SECONDS = 60 * 30


def _backup_if_due() -> None:
    try:
        manifest = backup_service.run_if_due(admin_db.get_setting)
        if manifest is None:
            return
        if manifest["verified"]:
            print(f"[backup] scheduled backup {manifest['name']} verified")
        else:
            print(f"[backup] scheduled backup {manifest['name']} FAILED: {manifest['errors']}")
    except Exception as exc:  # noqa: BLE001 - a failed backup must not stop the server
        print(f"[backup] scheduled backup failed: {exc}")


def _sweep_job_history() -> None:
    """Prunes settled job rows and old cleaning records. Runs at startup and on the
    same tick as the backup check - startup alone would never fire on a server that
    stays up for months, which is precisely the machine where the tables grow."""
    try:
        swept = housekeeping.sweep()
        if swept["jobs_removed"] or swept["cleaning_removed"]:
            print(
                f"[housekeeping] pruned {swept['jobs_removed']} finished job(s) and "
                f"{swept['cleaning_removed']} cleaning record(s)"
            )
    except Exception as exc:  # noqa: BLE001 - never let housekeeping stop the server
        print(f"[housekeeping] sweep failed: {exc}")


def _start_housekeeping() -> None:
    # The test harness sets this. Both of these write to the catalog on their own
    # schedule, which under a test suite means a thread deleting rows while an assertion
    # is reading them - a source of failures that appear and disappear with timing. The
    # functions themselves are called directly by the tests that cover them.
    if os.environ.get("DISABLE_BACKGROUND_SCHEDULES") == "1":
        return

    def loop() -> None:
        while True:
            _backup_if_due()
            _sweep_job_history()
            time.sleep(_SCHEDULE_CHECK_SECONDS)

    # a daemon thread: the schedule must never be the reason the process refuses to exit
    threading.Thread(target=loop, name="housekeeping", daemon=True).start()
