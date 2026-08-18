"""Admin control-panel endpoints: overview KPIs, activity feed, language settings and
system status. Everything here reports real state - nothing is stubbed."""

import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_permission
from app.config import settings
from app.db import admin as admin_db
from app.db import catalog
from app.models.schemas import (
    ActivityItem,
    ActivityPage,
    BackupOut,
    BackupPruneResult,
    BackupRequest,
    BackupSummary,
    LanguageOut,
    LockoutOut,
    OverviewOut,
    RetentionRequest,
    StorageCandidate,
    StorageCleanupRequest,
    StorageCleanupResult,
    StorageOverview,
    SystemStatusOut,
    UpdateLanguagesRequest,
)
from app.jobs import submit
from app.models.schemas import JobOut
from app.services import backup as backup_service
from app.services import login_guard
from app.services import storage as storage_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

_STARTED_AT = time.time()

# The languages the build actually ships translations for. Enabling one that has no
# bundle would show untranslated keys, so the list is fixed here and only the
# enabled/default flags are configurable.
SUPPORTED_LANGUAGES = [
    {"code": "ar", "name": "Arabic", "native_name": "العربية", "direction": "rtl"},
    {"code": "he", "name": "Hebrew", "native_name": "עברית", "direction": "rtl"},
    {"code": "en", "name": "English", "native_name": "English", "direction": "ltr"},
]

LANGUAGES_ENABLED_KEY = "languages.enabled"
LANGUAGES_DEFAULT_KEY = "languages.default"


def _enabled_languages() -> list[str]:
    return admin_db.get_setting(LANGUAGES_ENABLED_KEY, [l["code"] for l in SUPPORTED_LANGUAGES])


def _default_language() -> str:
    return admin_db.get_setting(LANGUAGES_DEFAULT_KEY, "ar")


def _activity_item(row: dict) -> ActivityItem:
    return ActivityItem(
        id=row["id"],
        at=str(row["occurred_at"]) if row.get("occurred_at") else None,
        actor_id=row.get("actor_id") or "",
        actor_username=row.get("actor_username") or "",
        action=row.get("action") or "",
        target_type=row.get("target_type") or "",
        target_id=row.get("target_id") or "",
        target_label=row.get("target_label") or "",
        detail=row.get("detail") or "",
    )


def _dir_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


@router.get("/overview", response_model=OverviewOut,
            dependencies=[Depends(require_permission("system.view"))])
def overview() -> OverviewOut:
    users = catalog.list_users()
    by_status: dict[str, int] = {}
    for u in users:
        status = u.get("status") or ("active" if u.get("is_active") else "inactive")
        by_status[status] = by_status.get(status, 0) + 1

    datasets = catalog.list_datasets()
    files_bytes = sum(int(d.get("raw_file_bytes") or 0) for d in datasets)
    files_rows = sum(int(d.get("row_count_raw") or 0) for d in datasets)

    recent, _ = admin_db.list_activity(limit=1)

    return OverviewOut(
        users_total=len(users),
        users_active=by_status.get("active", 0),
        users_by_status=by_status,
        roles_total=len(admin_db.list_roles()),
        permissions_total=len(admin_db.ALL_PERMISSION_KEYS),
        languages_enabled=len(_enabled_languages()),
        files_total=len(datasets),
        files_bytes=files_bytes,
        files_rows=files_rows,
        last_activity=_activity_item(recent[0]) if recent else None,
    )


@router.get("/activity", response_model=ActivityPage,
            dependencies=[Depends(require_permission("activity.view"))])
def activity(
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> ActivityPage:
    limit = min(max(limit, 1), 200)
    rows, total = admin_db.list_activity(limit=limit, offset=max(offset, 0), action=action, actor_id=actor_id)
    return ActivityPage(items=[_activity_item(r) for r in rows], total=total)


@router.get("/languages", response_model=list[LanguageOut],
            dependencies=[Depends(require_permission("languages.manage"))])
def languages() -> list[LanguageOut]:
    enabled = set(_enabled_languages())
    default = _default_language()
    return [
        LanguageOut(**l, enabled=l["code"] in enabled, is_default=l["code"] == default)
        for l in SUPPORTED_LANGUAGES
    ]


@router.patch("/languages", response_model=list[LanguageOut])
def update_languages(
    body: UpdateLanguagesRequest, actor: dict = Depends(require_permission("languages.manage"))
) -> list[LanguageOut]:
    codes = {l["code"] for l in SUPPORTED_LANGUAGES}

    if body.enabled is not None:
        unknown = sorted(set(body.enabled) - codes)
        if unknown:
            raise HTTPException(400, f"Unknown language(s): {', '.join(unknown)}")
        if not body.enabled:
            raise HTTPException(400, "At least one language must stay enabled")
        admin_db.set_setting(LANGUAGES_ENABLED_KEY, body.enabled)
        admin_db.log_activity(
            actor, "language.updated", "language", "", "", f"enabled={','.join(body.enabled)}"
        )

    if body.default is not None:
        if body.default not in codes:
            raise HTTPException(400, f"Unknown language: {body.default}")
        # a disabled default would leave the app with no usable language on first load
        if body.default not in set(_enabled_languages()):
            raise HTTPException(400, "The default language must be enabled")
        admin_db.set_setting(LANGUAGES_DEFAULT_KEY, body.default)
        admin_db.log_activity(actor, "language.default_changed", "language", body.default, body.default)

    return languages()


@router.get("/system", response_model=SystemStatusOut,
            dependencies=[Depends(require_permission("system.view"))])
def system_status() -> SystemStatusOut:
    uploads = _dir_bytes(settings.uploads_dir)
    datasets_bytes = _dir_bytes(settings.datasets_dir)
    exports = _dir_bytes(settings.exports_dir)
    catalog_bytes = settings.catalog_path.stat().st_size if settings.catalog_path.exists() else 0

    return SystemStatusOut(
        status="operational",
        data_dir=str(settings.data_dir),
        storage_bytes=uploads + datasets_bytes + exports + catalog_bytes,
        uploads_bytes=uploads,
        datasets_bytes=datasets_bytes,
        exports_bytes=exports,
        dataset_count=len(catalog.list_datasets()),
        started_at=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_STARTED_AT)),
        uptime_seconds=int(time.time() - _STARTED_AT),
    )


# ---- storage ---------------------------------------------------------------
#
# Deleting files is the one thing in this panel that cannot be undone, so the API is
# split in two: `plan` answers "what would go", `cleanup` does it. The UI always calls
# the first before offering the second.


@router.get("/storage", response_model=StorageOverview,
            dependencies=[Depends(require_permission("system.view"))])
def storage_overview() -> StorageOverview:
    data = storage_service.breakdown()
    return StorageOverview(**data, disk_free_bytes=storage_service.disk_free_bytes())


@router.get("/storage/plan", response_model=list[StorageCandidate],
            dependencies=[Depends(require_permission("system.view"))])
def storage_plan(
    expired_exports: bool = True,
    all_exports: bool = False,
    intermediates: bool = True,
) -> list[StorageCandidate]:
    """Exactly what a cleanup with these options would delete, and why."""
    candidates = storage_service.plan(
        expired_exports=expired_exports, all_exports=all_exports, intermediates=intermediates
    )
    return [StorageCandidate(**c.as_dict(settings.data_dir)) for c in candidates]


@router.post("/storage/cleanup", response_model=StorageCleanupResult)
def storage_cleanup(
    body: StorageCleanupRequest,
    actor: dict = Depends(require_permission("datasets.delete")),
) -> StorageCleanupResult:
    """Removes derived files. Originals and databases are refused at the service layer
    regardless of what is requested, so no combination of flags can delete data."""
    result = storage_service.cleanup(
        expired_exports=body.expired_exports,
        all_exports=body.all_exports,
        intermediates=body.intermediates,
    )
    admin_db.log_activity(
        actor,
        "storage.cleaned",
        "system",
        "storage",
        "",
        f"{result['removed_files']} file(s), {result['freed_bytes']} bytes",
    )
    return StorageCleanupResult(**result)


@router.patch("/storage/retention", response_model=StorageOverview)
def set_retention(
    body: RetentionRequest,
    actor: dict = Depends(require_permission("system.view")),
) -> StorageOverview:
    hours = storage_service.set_retention_hours(body.hours)
    admin_db.log_activity(
        actor, "storage.retention_changed", "system", "storage", "", f"{hours}h"
    )
    return storage_overview()


# ---- backups ----------------------------------------------------------------
#
# A backup runs as a job rather than inside the request: snapshotting several gigabytes
# takes longer than any sensible HTTP timeout, and the screen wants progress anyway.
#
# Every run verifies itself before reporting success, so `verified` on a listed backup
# means the file was reopened and its contents counted - not that the copy returned
# without raising.


@router.get("/backups", response_model=list[BackupOut],
            dependencies=[Depends(require_permission("system.view"))])
def list_backups() -> list[BackupOut]:
    return [BackupOut(**b) for b in backup_service.list_all()]


@router.get("/backups/summary", response_model=BackupSummary,
            dependencies=[Depends(require_permission("system.view"))])
def backup_summary() -> BackupSummary:
    return BackupSummary(**backup_service.summary())


@router.post("/backups", response_model=JobOut)
def start_backup(
    body: BackupRequest,
    actor: dict = Depends(require_permission("system.view")),
) -> JobOut:
    job_id = catalog.create_job("", "backup")
    admin_db.log_activity(
        actor, "backup.started", "system", "backup", "",
        "with originals" if body.include_originals else "databases only",
    )
    submit(_run_backup_job, job_id, body.include_originals)
    return JobOut(id=job_id, dataset_id="", kind="backup", status="pending", progress="")


def _run_backup_job(job_id: str, include_originals: bool) -> None:
    try:
        catalog.update_job(job_id, status="running", progress="starting")
        manifest = backup_service.run(
            include_originals=include_originals,
            progress=lambda stage: catalog.update_job(job_id, progress=stage),
        )
        if not manifest["verified"]:
            # the files are kept: an unverified backup is evidence, and deleting it would
            # destroy the only record of what went wrong
            catalog.update_job(
                job_id,
                status="error",
                progress="unverified",
                error_message="; ".join(manifest["errors"])[:2000],
                result_json=manifest,
            )
            return
        pruned = backup_service.prune()
        catalog.update_job(
            job_id, status="done", progress="ready",
            result_json={**manifest, "pruned": pruned},
        )
    except Exception as exc:  # noqa: BLE001 - the job record is where failures surface
        catalog.update_job(job_id, status="error", error_message=str(exc))


@router.post("/backups/prune", response_model=BackupPruneResult)
def prune_backups(actor: dict = Depends(require_permission("datasets.delete"))) -> BackupPruneResult:
    result = backup_service.prune()
    admin_db.log_activity(
        actor, "backup.pruned", "system", "backup", "", f"{result['removed']} removed"
    )
    return BackupPruneResult(**result)


@router.delete("/backups/{name}")
def delete_backup(
    name: str, actor: dict = Depends(require_permission("datasets.delete"))
) -> dict:
    if not backup_service.delete(name):
        raise HTTPException(404, "Backup not found")
    admin_db.log_activity(actor, "backup.deleted", "system", "backup", name, "")
    return {"deleted": name}


# ---- login lockouts ---------------------------------------------------------
#
# A lockout has to be visible and clearable by hand. It can be triggered by somebody else
# guessing at a colleague's username, and an invisible lock is one nobody can explain to
# the person waiting behind it.


@router.get("/lockouts", response_model=list[LockoutOut],
            dependencies=[Depends(require_permission("activity.view"))])
def list_lockouts() -> list[LockoutOut]:
    return [LockoutOut(**item) for item in login_guard.active_lockouts()]


@router.delete("/lockouts/{key:path}")
def clear_lockout(key: str, actor: dict = Depends(require_permission("users.update"))) -> dict:
    if not login_guard.clear(key):
        raise HTTPException(404, "No such lockout")
    admin_db.log_activity(actor, "auth.lockout_cleared", "user", "", key, "")
    return {"cleared": key}
