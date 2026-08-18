from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import admin as admin_db
from app.db import timestamp_migration
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
from app.services import storage
from app.services.security import bootstrap_admin

app = FastAPI(title="CSV Analyzer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
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
    # roles and permissions must exist before the first account is created, since the
    # bootstrap admin is given a role by slug
    admin_db.seed()

    # Corrects timestamps written before the UTC rule was settled. Records that it has
    # run, so it cannot shift the same rows twice.
    try:
        result = timestamp_migration.run(
            admin_db.get_connection(), admin_db.get_setting, admin_db.set_setting
        )
        if result.get("applied"):
            print(f"[startup] corrected {result['shifted_rows']:,} stored timestamps to UTC")
    except Exception as exc:  # noqa: BLE001 - never block startup over a migration
        print(f"[startup] timestamp migration failed: {exc}")

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
