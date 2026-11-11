"""One record, by its key: the vehicle card.

The grid shows a row as one line of a wide table, most of it off-screen. This returns
the whole record, every column, together with the two things recorded beside it: whether
a recent batch brought or replaced it, and the corrections made to it by hand.

Reading is `datasets.view`, like the grid - it is the same row. The corrections, and who
made them, go only to those who can make them (`datasets.edit`), exactly as the grid
shows its correction marks to them alone.
"""

from fastapi import APIRouter, Depends, Query

from app.auth import rate_limited, require_permission
from app.db import catalog
from app.db.connection import datasets as dataset_connections
from app.errors import ApiError
from app.models.schemas import CorrectionOut, RecordArrival, RecordOut
from app.services import arrivals, clocks, corrections, row_identity
from app.services.rate_limit import QUERY

router = APIRouter(prefix="/api/datasets", tags=["records"])

KEY_SEPARATOR = "\x1f"


@router.get(
    "/{dataset_id}/record",
    response_model=RecordOut,
    dependencies=[Depends(rate_limited(QUERY))],
)
def get_record(
    dataset_id: str,
    key: list[str] = Query(..., min_length=1, max_length=4),
    user: dict = Depends(require_permission("datasets.view")),
) -> RecordOut:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    if row.get("status") != "ready":
        raise ApiError(409, "dataset_not_ready", "This dataset has not finished importing")
    key_cols = row_identity.key_columns(row)
    if not key_cols:
        raise ApiError(
            409,
            "dataset_has_no_record_key",
            "This file has no record key, so a single record cannot be opened",
        )
    if len(key) != len(key_cols):
        raise ApiError(
            400,
            "key_wrong_length",
            f"This dataset's key has {len(key_cols)} columns",
        )

    row_key = KEY_SEPARATOR.join(key)
    with dataset_connections.reading(dataset_id):
        try:
            record = corrections.find_row(dataset_id, key_cols, key)
        except corrections.CorrectionProblem as exc:
            raise ApiError(409, exc.code, str(exc)) from exc
        if record is None:
            raise ApiError(404, "row_not_found", "No record with this key")
        arrival = arrivals.for_row(dataset_id, row_key)
        can_see_corrections = "datasets.edit" in set(user.get("permissions") or [])
        found = corrections.for_row(dataset_id, row_key) if can_see_corrections else None

    return RecordOut(
        columns=list(record),
        values=list(record.values()),
        key_columns=key_cols,
        key=key,
        arrival=(
            RecordArrival(kind=arrival["kind"], added_at=clocks.iso(arrival["added_at"]))
            if arrival
            else None
        ),
        corrections=(
            [
                CorrectionOut(
                    row_key=key,
                    column=c.get("column_name") or "",
                    old_value=c.get("old_value"),
                    new_value=c.get("new_value"),
                    actor=c.get("actor"),
                    edited_at=clocks.iso(c.get("edited_at")),
                )
                for c in found
            ]
            if found is not None
            else None
        ),
    )
