import json

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.db import catalog
from app.models.schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# Job ids are opaque UUIDs polled by several unrelated screens, so GET is left on
# authentication alone (see the system review). Cancelling is a write, though, and has
# to answer to the same permission the job's kind would have needed to start it -
# otherwise a viewer could reach in and stop someone else's import.
_CANCEL_PERMISSIONS = {
    "import": ("datasets.upload",),
    "quality": ("datasets.view",),
    "export": ("datasets.view", "datasets.export"),
    "backup": ("system.manage",),
    "compact": ("system.manage",),
}


def _job_out(row: dict) -> JobOut:
    result = json.loads(row["result_json"]) if row.get("result_json") else None
    return JobOut(
        id=row["id"],
        dataset_id=row["dataset_id"],
        kind=row["kind"],
        status=row["status"],
        progress=row.get("progress") or "",
        result=result,
        error_message=row.get("error_message"),
    )


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: dict = Depends(get_current_user)) -> JobOut:
    row = catalog.get_job(job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    return _job_out(row)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, user: dict = Depends(get_current_user)) -> JobOut:
    row = catalog.get_job(job_id)
    if row is None:
        raise HTTPException(404, "Job not found")

    needed = _CANCEL_PERMISSIONS.get(row["kind"], ())
    granted = set(user.get("permissions") or [])
    if not all(k in granted for k in needed):
        raise HTTPException(403, "You do not have permission to perform this action")

    if row["status"] not in ("pending", "running"):
        # Already finished, or a cancel already went through - nothing to do, and the
        # caller can tell from the status it gets back either way.
        return _job_out(row)

    catalog.request_job_cancel(job_id)
    return _job_out(catalog.get_job(job_id))
