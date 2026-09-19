"""Correcting a record, and reading back what has been corrected.

Every route here needs `datasets.edit`, which is seeded to the administrator roles
alone. A correction overwrites what the source file said about a real vehicle, and the
file is the record - so this is deliberately not something an editor who uploads and
cleans can do.

The corrections themselves live in the dataset file rather than here; see
app/services/corrections.py for why they are kept apart from the data they change.
"""

from fastapi import APIRouter, Depends

from app.auth import require_permission
from app.db import admin as admin_db
from app.db import catalog
from app.db.connection import datasets as dataset_connections
from app.errors import ApiError
from app.models.schemas import CorrectionOut, RowEdit, RowEditResult
from app.services import clocks, corrections, row_identity, sql_utils

router = APIRouter(prefix="/api/datasets", tags=["rows"])

KEY_SEPARATOR = "\x1f"


def _dataset_with_key(dataset_id: str) -> tuple[dict, list[str]]:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    if row.get("status") != "ready":
        raise ApiError(409, "dataset_not_ready", "This dataset has not finished importing")
    key_cols = row_identity.key_columns(row)
    if not key_cols:
        raise ApiError(
            409,
            "dataset_has_no_key",
            "Say which columns identify a record before correcting one",
        )
    return row, key_cols


def _correction_out(record: dict) -> CorrectionOut:
    return CorrectionOut(
        row_key=str(record.get("row_key") or "").split(KEY_SEPARATOR),
        column=record.get("column_name") or "",
        old_value=record.get("old_value"),
        new_value=record.get("new_value"),
        actor=record.get("actor"),
        edited_at=clocks.iso(record.get("edited_at")),
    )


@router.patch("/{dataset_id}/rows", response_model=RowEditResult)
def edit_row(
    dataset_id: str,
    body: RowEdit,
    user: dict = Depends(require_permission("datasets.edit")),
) -> RowEditResult:
    row_meta, key_cols = _dataset_with_key(dataset_id)
    if len(body.key) != len(key_cols):
        raise ApiError(
            400,
            "key_wrong_length",
            f"This dataset's key has {len(key_cols)} columns",
        )

    available = sql_utils.table_columns(dataset_id, "raw_data")
    unknown = [c for c in body.changes if c not in set(available)]
    if unknown:
        raise ApiError(400, "unknown_column", f"No such column: {', '.join(unknown)}")

    # Changing a key column would change which record this is, so the correction could
    # not be addressed afterwards and an appended batch would no longer recognise it.
    # It is a different operation - removing one record and adding another - and saying
    # so is better than doing half of it.
    touching_key = [c for c in body.changes if c in set(key_cols)]
    if touching_key:
        raise ApiError(
            422,
            "cannot_edit_key_column",
            f"{', '.join(touching_key)} identifies the record and cannot be corrected",
        )

    try:
        current = corrections.find_row(dataset_id, key_cols, body.key)
    except corrections.CorrectionProblem as exc:
        raise ApiError(409, exc.code, str(exc)) from exc
    if current is None:
        raise ApiError(404, "row_not_found", "No record with this key")

    corrections.ensure_table(dataset_id)
    row_key = KEY_SEPARATOR.join(body.key)
    actor = user.get("username") or user.get("id") or ""

    with dataset_connections.write_lock(dataset_id):
        cur = dataset_connections.cursor(dataset_id)
        where = " AND ".join(
            f"COALESCE({sql_utils.quote_ident(c)}, '') = ?" for c in key_cols
        )
        for column, value in body.changes.items():
            corrections.record(
                dataset_id, row_key, column, current.get(column), value, actor
            )
            quoted = sql_utils.quote_ident(column)
            cur.execute(
                f"UPDATE raw_data SET {quoted} = ? WHERE {where}", [value, *body.key]
            )
            # the cleaned table is a projection of raw_data, so it holds the column only
            # if the reader kept it
            if sql_utils.table_exists(dataset_id, "cleaned_data") and column in set(
                sql_utils.table_columns(dataset_id, "cleaned_data")
            ):
                cur.execute(
                    f"UPDATE cleaned_data SET {quoted} = ? WHERE {where}",
                    [value, *body.key],
                )

    admin_db.log_activity(
        user,
        "dataset.row_corrected",
        "dataset",
        dataset_id,
        row_meta.get("original_filename") or "",
        f"{', '.join(body.changes)} for {row_key}",
        detail_code="row_corrected",
        count=len(body.changes),
        fields=", ".join(body.changes),
    )

    updated = corrections.find_row(dataset_id, key_cols, body.key) or {}
    stored = [
        c
        for c in corrections.listing(dataset_id, limit=1000)
        if c.get("row_key") == row_key
    ]
    return RowEditResult(
        columns=available,
        row=[updated.get(c) for c in available],
        corrections=[_correction_out(c) for c in stored],
    )


@router.get("/{dataset_id}/corrections")
def list_corrections(
    dataset_id: str,
    limit: int = 200,
    offset: int = 0,
    user: dict = Depends(require_permission("datasets.edit")),
) -> dict:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    limit = min(max(limit, 1), 500)
    return {
        "total": corrections.count(dataset_id),
        "items": [
            _correction_out(c) for c in corrections.listing(dataset_id, limit, max(offset, 0))
        ],
    }


@router.delete("/{dataset_id}/corrections", response_model=RowEditResult)
def revert_correction(
    dataset_id: str,
    body: RowEdit,
    user: dict = Depends(require_permission("datasets.edit")),
) -> RowEditResult:
    """Puts the file's own value back.

    `changes` carries the columns to revert; its values are ignored, so the interface
    can send the same shape it sends to edit.
    """
    row_meta, key_cols = _dataset_with_key(dataset_id)
    row_key = KEY_SEPARATOR.join(body.key)

    reverted: list[str] = []
    with dataset_connections.write_lock(dataset_id):
        cur = dataset_connections.cursor(dataset_id)
        where = " AND ".join(
            f"COALESCE({sql_utils.quote_ident(c)}, '') = ?" for c in key_cols
        )
        for column in body.changes:
            previous = corrections.forget(dataset_id, row_key, column)
            if previous is None:
                continue
            quoted = sql_utils.quote_ident(column)
            cur.execute(
                f"UPDATE raw_data SET {quoted} = ? WHERE {where}",
                [previous["old_value"], *body.key],
            )
            if sql_utils.table_exists(dataset_id, "cleaned_data") and column in set(
                sql_utils.table_columns(dataset_id, "cleaned_data")
            ):
                cur.execute(
                    f"UPDATE cleaned_data SET {quoted} = ? WHERE {where}",
                    [previous["old_value"], *body.key],
                )
            reverted.append(column)

    if not reverted:
        raise ApiError(404, "correction_not_found", "Nothing was corrected here")

    admin_db.log_activity(
        user,
        "dataset.row_reverted",
        "dataset",
        dataset_id,
        row_meta.get("original_filename") or "",
        f"{', '.join(reverted)} for {row_key}",
        detail_code="row_reverted",
        count=len(reverted),
        fields=", ".join(reverted),
    )

    available = sql_utils.table_columns(dataset_id, "raw_data")
    updated = corrections.find_row(dataset_id, key_cols, body.key) or {}
    stored = [
        c
        for c in corrections.listing(dataset_id, limit=1000)
        if c.get("row_key") == row_key
    ]
    return RowEditResult(
        columns=available,
        row=[updated.get(c) for c in available],
        corrections=[_correction_out(c) for c in stored],
    )
