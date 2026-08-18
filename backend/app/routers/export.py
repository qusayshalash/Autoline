import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.auth import require_permission
from app.config import settings
from app.db import catalog
from app.models.schemas import ExportRequest, JobOut
from app.services import export as export_service

router = APIRouter(prefix="/api/datasets", tags=["export"])

_MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.post("/{dataset_id}/export", response_model=JobOut)
def request_export(dataset_id: str, req: ExportRequest, user: dict = Depends(require_permission("datasets.export"))) -> JobOut:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    if row["status"] != "ready":
        raise HTTPException(409, f"Dataset is not ready (status={row['status']})")
    try:
        job_id = export_service.start_export(dataset_id, req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JobOut(id=job_id, dataset_id=dataset_id, kind="export", status="pending", progress="")


@router.get("/{dataset_id}/export/{job_id}/download")
def download_export(dataset_id: str, job_id: str, user: dict = Depends(require_permission("datasets.export"))) -> FileResponse:
    job = catalog.get_job(job_id)
    if job is None or job["dataset_id"] != dataset_id:
        raise HTTPException(404, "Export job not found")
    if job["status"] != "done":
        raise HTTPException(409, f"Export not ready (status={job['status']})")

    result = json.loads(job["result_json"]) if job.get("result_json") else {}
    fmt = result.get("format", "csv")
    path = settings.exports_dir / dataset_id / f"{job_id}.{fmt}"
    if not path.exists():
        raise HTTPException(410, "Export file no longer available")
    return FileResponse(path, media_type=_MEDIA_TYPES.get(fmt, "application/octet-stream"), filename=path.name)
