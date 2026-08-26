"""Breakdown endpoints for the Statistics dashboard.

Two shapes of the same query. POST takes the typed body the dashboard sends (filter
lists get long once a few chips are active, and bodies don't hit URL length limits).
GET takes the documented query-string form - `?group_by=sug_delek_nm&filters=[...]` -
which makes a statistic linkable and testable with curl.
"""

import json
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError

from app.auth import require_permission
from app.db import catalog
from app.models.schemas import (
    ColumnSuggestion,
    PivotOut,
    PivotQuery,
    StatisticsExportRequest,
    StatisticsOut,
    StatisticsQuery,
)
from app.services import analytics, statistics_export

router = APIRouter(prefix="/api/datasets", tags=["statistics"])


def _require_ready(dataset_id: str) -> dict:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    if row["status"] != "ready":
        raise HTTPException(409, f"Dataset is not ready (status={row['status']})")
    return row


def _compute(dataset_id: str, q: StatisticsQuery) -> StatisticsOut:
    _require_ready(dataset_id)
    try:
        return analytics.compute(dataset_id, q)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{dataset_id}/statistics", response_model=StatisticsOut)
def post_statistics(
    dataset_id: str,
    q: StatisticsQuery,
    user: dict = Depends(require_permission("datasets.view")),
) -> StatisticsOut:
    return _compute(dataset_id, q)


@router.get("/{dataset_id}/statistics", response_model=StatisticsOut)
def get_statistics(
    dataset_id: str,
    group_by: str,
    filters: Optional[str] = None,
    search: Optional[str] = None,
    source: Literal["raw", "cleaned"] = "cleaned",
    limit: int = 50,
    sort: Literal["count", "value"] = "count",
    granularity: Literal["year", "month", "day"] = "year",
    bins: int = 20,
    user: dict = Depends(require_permission("datasets.view")),
) -> StatisticsOut:
    """`filters` is a JSON array of filter rules, e.g.
    `[{"column":"tozeret_nm","op":"contains","value":"קיה"}]`."""
    parsed: list = []
    if filters:
        try:
            parsed = json.loads(filters)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"filters is not valid JSON: {exc}") from exc
        if not isinstance(parsed, list):
            raise HTTPException(400, "filters must be a JSON array of rules")

    try:
        q = StatisticsQuery(
            group_by=group_by,
            filters=parsed,
            search=search,
            source=source,
            limit=limit,
            sort=sort,
            granularity=granularity,
            bins=bins,
        )
    except ValidationError as exc:
        raise HTTPException(400, exc.errors(include_url=False)) from exc

    return _compute(dataset_id, q)


@router.post("/{dataset_id}/pivot", response_model=PivotOut)
def post_pivot(
    dataset_id: str,
    q: PivotQuery,
    user: dict = Depends(require_permission("datasets.view")),
) -> PivotOut:
    """A cross-tab of two columns over the same subset a breakdown would describe."""
    _require_ready(dataset_id)
    try:
        return analytics.compute_pivot(dataset_id, q)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{dataset_id}/statistics/export")
def export_statistics(
    dataset_id: str,
    req: StatisticsExportRequest,
    user: dict = Depends(require_permission("datasets.export")),
) -> Response:
    """Returns the current breakdown as a file, built and sent on this request.

    Nothing is written to disk: these files are a few kilobytes, and the exports folder
    is for full data extracts, which are measured in hundreds of megabytes.
    """
    _require_ready(dataset_id)
    try:
        content = statistics_export.build(req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    name = (req.title or "statistics").strip() or "statistics"
    filename = f"{name}.{req.format}"
    return Response(
        content=content,
        media_type=statistics_export.MEDIA_TYPES[req.format],
        headers={
            # RFC 5987: the plain filename stays ASCII-safe for old clients while the
            # Arabic or Hebrew title survives in filename*
            "Content-Disposition": (
                f"attachment; filename=\"statistics.{req.format}\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.get("/{dataset_id}/statistics/columns", response_model=list[ColumnSuggestion])
def get_column_suggestions(
    dataset_id: str,
    source: Literal["raw", "cleaned"] = "cleaned",
    user: dict = Depends(require_permission("datasets.view")),
) -> list[ColumnSuggestion]:
    _require_ready(dataset_id)
    return analytics.suggest_columns(dataset_id, source)
