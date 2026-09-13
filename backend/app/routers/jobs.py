import json

from fastapi import APIRouter, Depends, HTTPException

from app.errors import ApiError
from app.auth import get_current_user
from app.db import catalog
from app.models.schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# What a job's kind answers to, for reading it as well as for cancelling it: whatever
# that kind of job would have needed to be started in the first place.
#
# Cancelling was guarded from the start. Reading was not - a job id is an opaque UUID,
# and leaving GET on authentication alone was judged good enough while the rest of the
# review was going on. It is not: an account holding no permissions at all could read
# any job it had the id of, and a finished export job carries the dataset id, the file
# name and its size. Guessing a UUID is not the threat; being handed one, by a log or a
# shared link or a screen someone left open, is.
#
# An unlisted kind is refused rather than allowed. A new kind of job added without a
# line here then fails visibly for everyone, which is a bug somebody reports on the
# first day, instead of quietly being readable by anyone signed in.
_JOB_PERMISSIONS = {
    "import": ("datasets.upload",),
    "quality": ("datasets.view",),
    "export": ("datasets.view", "datasets.export"),
    "backup": ("system.manage",),
    "compact": ("system.manage",),
}


def _require_job_access(row: dict, user: dict) -> None:
    needed = _JOB_PERMISSIONS.get(row["kind"])
    granted = set(user.get("permissions") or [])
    if needed is None or not all(k in granted for k in needed):
        raise ApiError(403, "forbidden", "You do not have permission to perform this action")


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
        raise ApiError(404, "job_not_found", "Job not found")
    _require_job_access(row, user)
    return _job_out(row)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, user: dict = Depends(get_current_user)) -> JobOut:
    row = catalog.get_job(job_id)
    if row is None:
        raise ApiError(404, "job_not_found", "Job not found")

    _require_job_access(row, user)

    if row["status"] not in ("pending", "running"):
        # Already finished, or a cancel already went through - nothing to do, and the
        # caller can tell from the status it gets back either way.
        return _job_out(row)

    catalog.request_job_cancel(job_id)
    return _job_out(catalog.get_job(job_id))
