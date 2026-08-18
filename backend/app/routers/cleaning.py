from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_permission
from app.db import admin as admin_db
from app.db import catalog
from app.models.schemas import CleaningConfig, CleaningResult
from app.services import cleaning

router = APIRouter(prefix="/api/datasets", tags=["cleaning"])


@router.post("/{dataset_id}/clean", response_model=CleaningResult)
def clean_dataset(
    dataset_id: str, config: CleaningConfig, user: dict = Depends(require_permission("datasets.clean"))
) -> CleaningResult:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    if row["status"] not in ("ready",):
        raise HTTPException(409, f"Dataset is not ready for cleaning (status={row['status']})")
    try:
        result = cleaning.apply_cleaning(dataset_id, config)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    admin_db.log_activity(
        user, "dataset.cleaned", "dataset", dataset_id, row.get("original_filename") or "",
        f"{result.rows_before:,} -> {result.rows_after:,} rows",
    )
    return result


@router.get("/{dataset_id}/cleaning-operations")
def get_cleaning_history(dataset_id: str, user: dict = Depends(get_current_user)) -> list[dict]:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    return catalog.list_cleaning_operations(dataset_id)
