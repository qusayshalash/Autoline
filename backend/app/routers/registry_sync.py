"""Synchronising a dataset with the government vehicle registry.

Seeing the state needs `system.view`; choosing the dataset, previewing and applying need
`system.manage` - applying rewrites a large part of a dataset, and choosing which one is
a statement about what the system is for.
"""

from fastapi import APIRouter, Depends

from app.auth import require_permission
from app.db import admin as admin_db
from app.db import catalog
from app.errors import ApiError
from app.jobs import submit
from app.models.schemas import JobOut, RegistrySyncApply, RegistrySyncConfig
from app.services import registry_sync, row_identity

router = APIRouter(prefix="/api/admin/registry-sync", tags=["registry-sync"])


def _status() -> dict:
    dataset_id = admin_db.get_setting(registry_sync.DATASET_KEY)
    dataset = catalog.get_dataset(dataset_id) if dataset_id else None
    return {
        "dataset_id": dataset_id if dataset else None,
        "dataset_name": (dataset or {}).get("original_filename"),
        "schedule": admin_db.get_setting(registry_sync.SCHEDULE_KEY, "off"),
        "running": registry_sync.RUN_LOCK.locked(),
        "preview": registry_sync.current_preview(),
        "last_report": admin_db.get_setting(registry_sync.LAST_REPORT_KEY),
        "source": {
            "resource_id": registry_sync.RESOURCE_ID,
            "page": f"https://data.gov.il/dataset/private-and-commercial-vehicles/resource/{registry_sync.RESOURCE_ID}",
        },
    }


@router.get("", dependencies=[Depends(require_permission("system.view"))])
def get_status() -> dict:
    return _status()


@router.put("")
def set_config(
    body: RegistrySyncConfig, actor: dict = Depends(require_permission("system.manage"))
) -> dict:
    if body.dataset_id:
        row = catalog.get_dataset(body.dataset_id)
        if row is None:
            raise ApiError(404, "dataset_not_found", "Dataset not found")
        if not row_identity.key_columns(row):
            raise ApiError(
                409, "registry_sync_needs_key", "The dataset needs a record key to be synchronised"
            )
    if body.schedule == "daily" and not body.dataset_id:
        raise ApiError(
            400, "registry_sync_needs_dataset", "Choose the dataset to synchronise first"
        )
    previous = admin_db.get_setting(registry_sync.DATASET_KEY)
    admin_db.set_setting(registry_sync.DATASET_KEY, body.dataset_id)
    admin_db.set_setting(registry_sync.SCHEDULE_KEY, body.schedule)
    # A preview and a history are statements about one dataset: whatever belongs to
    # another goes. A preview of the dataset just chosen stays - choosing it is not a
    # reason to throw away the comparison that was made of it.
    preview = registry_sync.current_preview()
    if preview and preview.get("dataset_id") != body.dataset_id:
        registry_sync.discard_preview()
    if previous and previous != body.dataset_id:
        admin_db.set_setting(registry_sync.LAST_REPORT_KEY, None)
        admin_db.set_setting(registry_sync.LAST_SOURCE_KEY, None)
    admin_db.log_activity(
        actor, "registry.configured", "system", "registry_sync", "",
        f"schedule={body.schedule}", detail_code="registry_schedule", schedule=body.schedule,
    )
    return _status()


def _start(kind: str, dataset_id: str, work) -> JobOut:
    if not registry_sync.RUN_LOCK.acquire(blocking=False):
        raise ApiError(409, "registry_sync_busy", "A registry sync is already running")
    try:
        job_id = catalog.create_job(dataset_id, kind)
    except Exception:
        registry_sync.RUN_LOCK.release()
        raise

    def run() -> None:
        try:
            catalog.update_job(job_id, status="running", progress="starting")
            result = work(lambda stage: catalog.update_job(job_id, progress=stage),
                          lambda: catalog.is_cancelling(job_id))
            catalog.update_job(job_id, status="done", progress="ready", result_json=result)
        except registry_sync.SyncProblem as exc:
            status = "cancelled" if exc.code == "registry_sync_cancelled" else "error"
            catalog.update_job(job_id, status=status, error_message=exc.code)
        except Exception as exc:  # noqa: BLE001 - the job record is where failures surface
            catalog.update_job(job_id, status="error", error_message=str(exc))
        finally:
            registry_sync.RUN_LOCK.release()

    submit(run)
    return JobOut(id=job_id, dataset_id=dataset_id, kind=kind, status="pending", progress="")


@router.post("/preview", response_model=JobOut)
def start_preview(actor: dict = Depends(require_permission("system.manage"))) -> JobOut:
    dataset_id = admin_db.get_setting(registry_sync.DATASET_KEY)
    if not dataset_id or catalog.get_dataset(dataset_id) is None:
        raise ApiError(400, "registry_sync_needs_dataset", "Choose the dataset to synchronise first")
    admin_db.log_activity(actor, "registry.previewed", "dataset", dataset_id, "", "")
    return _start(
        "registry_preview",
        dataset_id,
        lambda progress, cancel: _summary(
            registry_sync.preview(dataset_id, progress=progress, should_cancel=cancel)
        ),
    )


@router.post("/apply", response_model=JobOut)
def start_apply(
    body: RegistrySyncApply, actor: dict = Depends(require_permission("system.manage"))
) -> JobOut:
    report = registry_sync.current_preview()
    if report is None:
        raise ApiError(409, "registry_no_preview", "Preview the sync before applying it")
    return _start(
        "registry_apply",
        report["dataset_id"],
        lambda progress, _cancel: registry_sync.apply(actor, body.baseline, progress=progress),
    )


@router.delete("/preview")
def discard_preview(actor: dict = Depends(require_permission("system.manage"))) -> dict:
    if registry_sync.RUN_LOCK.locked():
        raise ApiError(409, "registry_sync_busy", "A registry sync is already running")
    registry_sync.discard_preview()
    return _status()


def _summary(report: dict) -> dict:
    """What the job record keeps: the counts, not the lists."""
    return {k: report[k] for k in ("new", "changed", "removed", "returned") if k in report}
