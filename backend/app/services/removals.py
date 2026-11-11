"""Records the government registry no longer lists - kept, and marked.

When a vehicle leaves the registry (scrapped, exported, off the road) the synchronised
dataset does not delete it: the record is still true about the past, and somebody looking
it up should find it and be told it is gone rather than find nothing. So the key is noted
here, with the day it was first missed, and the grid marks the row.

The same shape as arrivals: a small table beside the data, keyed by the record key, so a
re-import that rebuilds raw_data leaves it untouched. Unlike arrivals it never expires -
a vehicle that left the registry has left it until it comes back, and a sync that finds
it again takes the mark off.
"""

from typing import Optional

from app.db.connection import datasets
from app.services import row_identity, sql_utils

TABLE = "row_removals"


def ensure_table(dataset_id: str) -> None:
    """Created on the first sync that finds something missing; most files never need it."""
    datasets.cursor(dataset_id).execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            row_key    VARCHAR PRIMARY KEY,
            removed_at TIMESTAMP
        )
        """
    )


def summary(dataset_id: str) -> Optional[dict]:
    """How many records are marked removed, for the screen to offer the filter at all."""
    if not sql_utils.table_exists(dataset_id, TABLE):
        return None
    count, latest = (
        datasets.cursor(dataset_id)
        .execute(f"SELECT COUNT(*), MAX(removed_at) FROM {TABLE}")
        .fetchone()
    )
    return {"count": count, "latest_at": latest} if count else None


def mark_page(dataset_id: str, key_columns: list[str], rows: list, columns: list[str]) -> list:
    """For each row of one page, whether it is marked removed. Same reasoning as
    arrivals.mark_page: ask about the hundred keys in hand, never join the whole table."""
    if not key_columns or not rows or not sql_utils.table_exists(dataset_id, TABLE):
        return [False] * len(rows)
    indexes = [columns.index(c) for c in key_columns if c in columns]
    if len(indexes) != len(key_columns):
        return [False] * len(rows)
    keys = ["\x1f".join(str(row[i] or "") for i in indexes) for row in rows]
    placeholders = ", ".join("?" for _ in keys)
    found = {
        k
        for (k,) in datasets.cursor(dataset_id)
        .execute(f"SELECT row_key FROM {TABLE} WHERE row_key IN ({placeholders})", keys)
        .fetchall()
    }
    return [key in found for key in keys]


def filter_sql(dataset_id: str, key_columns: list[str]) -> Optional[str]:
    """A WHERE fragment keeping only rows marked removed, or None when there are none."""
    if not key_columns or not sql_utils.table_exists(dataset_id, TABLE):
        return None
    key_expr = row_identity.key_expression(key_columns)
    return f"{key_expr} IN (SELECT row_key FROM {TABLE})"


def for_row(dataset_id: str, row_key: str) -> Optional[str]:
    """When this record was first missed from the registry, or None."""
    if not sql_utils.table_exists(dataset_id, TABLE):
        return None
    found = (
        datasets.cursor(dataset_id)
        .execute(f"SELECT removed_at FROM {TABLE} WHERE row_key = ?", [row_key])
        .fetchone()
    )
    return found[0] if found else None
