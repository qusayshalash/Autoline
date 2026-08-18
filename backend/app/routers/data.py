from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.db import catalog
from app.models.schemas import (
    ColumnsOut,
    DataPage,
    DataQuery,
    DistinctValuesOut,
    GroupPage,
    GroupQuery,
    StatsOut,
)
from app.services import query as query_service
from app.services import stats as stats_service

router = APIRouter(prefix="/api/datasets", tags=["data"])


def _require_ready(dataset_id: str) -> dict:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    if row["status"] not in ("ready",):
        raise HTTPException(409, f"Dataset is not ready (status={row['status']})")
    return row


@router.post("/{dataset_id}/data", response_model=DataPage)
def get_data(dataset_id: str, q: DataQuery, user: dict = Depends(get_current_user)) -> DataPage:
    _require_ready(dataset_id)
    try:
        return query_service.fetch_page(dataset_id, q)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{dataset_id}/data", response_model=DataPage)
def get_data_get(
    dataset_id: str,
    page: int = 1,
    page_size: int = 100,
    sort_by: Optional[str] = None,
    sort_dir: Literal["asc", "desc"] = "asc",
    search: Optional[str] = None,
    source: Literal["raw", "cleaned"] = "cleaned",
    user: dict = Depends(get_current_user),
) -> DataPage:
    """GET variant for simple browsing (no filters) - handy for shareable links / bookmarking."""
    _require_ready(dataset_id)
    q = DataQuery(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
        filters=[],
        source=source,
    )
    try:
        return query_service.fetch_page(dataset_id, q)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{dataset_id}/data/distinct-values", response_model=DistinctValuesOut)
def get_distinct_values(
    dataset_id: str,
    column: str,
    search: Optional[str] = None,
    source: Literal["raw", "cleaned"] = "cleaned",
    limit: Optional[int] = None,
    user: dict = Depends(get_current_user),
) -> DistinctValuesOut:
    _require_ready(dataset_id)
    try:
        return query_service.distinct_values(dataset_id, source, column, search, limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{dataset_id}/group", response_model=GroupPage)
def get_groups(dataset_id: str, q: GroupQuery, user: dict = Depends(get_current_user)) -> GroupPage:
    _require_ready(dataset_id)
    try:
        return query_service.fetch_groups(dataset_id, q)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{dataset_id}/columns", response_model=ColumnsOut)
def get_columns(
    dataset_id: str,
    source: Literal["raw", "cleaned"] = "cleaned",
    user: dict = Depends(get_current_user),
) -> ColumnsOut:
    _require_ready(dataset_id)
    return query_service.column_types(dataset_id, source)


@router.get("/{dataset_id}/stats", response_model=StatsOut)
def get_stats(dataset_id: str, user: dict = Depends(get_current_user)) -> StatsOut:
    _require_ready(dataset_id)
    return stats_service.get_stats(dataset_id)
