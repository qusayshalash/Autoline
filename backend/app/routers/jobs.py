import json

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.db import catalog
from app.models.schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: dict = Depends(get_current_user)) -> JobOut:
    row = catalog.get_job(job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
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
