from app.db import catalog
from app.models.schemas import StatsOut
from app.services import sql_utils


def get_stats(dataset_id: str) -> StatsOut:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ValueError(f"Dataset not found: {dataset_id}")

    ops = catalog.list_cleaning_operations(dataset_id)
    latest = ops[0] if ops else None

    raw_bytes = row.get("raw_file_bytes") or 0
    cleaned_bytes = row.get("cleaned_file_bytes")
    reduction_pct = None
    if raw_bytes and cleaned_bytes is not None:
        reduction_pct = round((raw_bytes - cleaned_bytes) / raw_bytes * 100, 2)

    active_table = sql_utils.resolve_source_table(dataset_id, "cleaned")
    columns = sql_utils.table_columns(dataset_id, active_table)

    return StatsOut(
        row_count_raw=row.get("row_count_raw") or 0,
        row_count_cleaned=row.get("row_count_cleaned"),
        duplicates_removed=(latest["duplicates_removed"] if latest else 0),
        filtered_out=(latest["filtered_out"] if latest else 0),
        raw_file_bytes=raw_bytes,
        cleaned_file_bytes=cleaned_bytes,
        reduction_pct=reduction_pct,
        columns=columns,
    )
