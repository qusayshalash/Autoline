"""Which records arrived recently, and whether they were new or an update.

A batch of two hundred thousand rows lands somewhere in four million, and "somewhere" is
the problem: the table has no order the reader can rely on - `fetch_page` adds no ORDER
BY unless one is asked for, so position is storage order, which an upsert changes anyway
by deleting a row and appending it again. Scrolling to the end is not a way to see what
came in.

So arrivals are recorded rather than inferred, in a table of their own beside the data,
the same shape as corrections. Two things follow from that choice:

**It expires, and that is the point.** A "new" badge that never fades stops being read
within a week; one that is only there while the information is fresh keeps meaning
something. The window is a setting, defaulting to seven days.

**It stays small by construction.** Nothing outside the window is worth keeping, so every
append sweeps what has aged out. The table holds one recent batch or two, never a history,
however many years the registry runs.

New and updated are kept apart because they answer different questions - "what vehicles
do we now have" and "what changed about the ones we had" - and a reader scanning a page
wants to tell them at a glance rather than compare against memory.
"""

from datetime import timedelta
from typing import Optional

from app.db import admin as admin_db
from app.db.connection import datasets
from app.services import clocks, row_identity, sql_utils

TABLE = "row_arrivals"

WINDOW_KEY = "arrivals.window_days"
DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 90

NEW = "new"
UPDATED = "updated"


def window_days() -> int:
    """How long an arrival stays worth pointing at."""
    try:
        value = int(admin_db.get_setting(WINDOW_KEY, DEFAULT_WINDOW_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_DAYS
    return max(1, min(value, MAX_WINDOW_DAYS))


def set_window_days(days: int) -> int:
    days = max(1, min(int(days), MAX_WINDOW_DAYS))
    admin_db.set_setting(WINDOW_KEY, days)
    return days


def ensure_table(dataset_id: str) -> None:
    """Created on first append rather than at startup: most datasets never take one."""
    cur = datasets.cursor(dataset_id)
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            row_key  VARCHAR PRIMARY KEY,
            kind     VARCHAR,
            added_at TIMESTAMP
        )
        """
    )


def sweep(dataset_id: str) -> int:
    """Forgets arrivals older than the window. Returns how many were dropped."""
    if not sql_utils.table_exists(dataset_id, TABLE):
        return 0
    cutoff = clocks.now() - timedelta(days=window_days())
    cur = datasets.cursor(dataset_id)
    before = cur.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    cur.execute(f"DELETE FROM {TABLE} WHERE added_at < ?", [cutoff])
    after = cur.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    return before - after


def record_batch(dataset_id: str, key_columns: list[str]) -> dict:
    """Notes every key in `incoming_batch` as new or updated. Caller holds the lock.

    Run *before* the incoming rows are merged, while raw_data still holds only what was
    there beforehand - that is what makes "was this record already here" answerable at
    all. A key seen again inside the window keeps its first classification: a vehicle
    that arrived last Tuesday and was restated today is still, to a reader, the vehicle
    that arrived last Tuesday.
    """
    if not key_columns:
        return {"new": 0, "updated": 0}

    ensure_table(dataset_id)
    cur = datasets.cursor(dataset_id)
    incoming_key = row_identity.key_expression(key_columns, "i")
    existing_key = row_identity.key_expression(key_columns, "r")
    now = clocks.now()

    cur.execute(
        f"""
        INSERT INTO {TABLE} (row_key, kind, added_at)
        SELECT {incoming_key},
               CASE WHEN EXISTS (
                   SELECT 1 FROM raw_data r WHERE {existing_key} = {incoming_key}
               ) THEN '{UPDATED}' ELSE '{NEW}' END,
               ?
        FROM incoming_batch i
        ON CONFLICT (row_key) DO UPDATE SET added_at = excluded.added_at
        """,
        [now],
    )
    counts = dict(
        cur.execute(
            f"SELECT kind, COUNT(*) FROM {TABLE} WHERE added_at = ? GROUP BY kind", [now]
        ).fetchall()
    )
    return {"new": counts.get(NEW, 0), "updated": counts.get(UPDATED, 0)}


def summary(dataset_id: str) -> Optional[dict]:
    """How many recent arrivals there are, for the screen to offer a filter at all."""
    if not sql_utils.table_exists(dataset_id, TABLE):
        return None
    cur = datasets.cursor(dataset_id)
    rows = cur.execute(
        f"SELECT kind, COUNT(*), MAX(added_at) FROM {TABLE} GROUP BY kind"
    ).fetchall()
    if not rows:
        return None
    counts = {kind: n for kind, n, _ in rows}
    latest = max(when for _, _, when in rows if when is not None)
    return {
        "new": counts.get(NEW, 0),
        "updated": counts.get(UPDATED, 0),
        "latest_at": latest,
        "window_days": window_days(),
    }


def mark_page(dataset_id: str, key_columns: list[str], rows: list, columns: list[str]) -> list:
    """For each row of one page, "new", "updated" or None.

    A second small query rather than a join on the main one. The page is already in
    hand - a hundred rows - so this asks about a hundred keys; joining instead would
    make every reader pay, on every page, to discover that almost no row is recent.
    """
    if not key_columns or not rows:
        return [None] * len(rows)
    if not sql_utils.table_exists(dataset_id, TABLE):
        return [None] * len(rows)

    indexes = [columns.index(c) for c in key_columns if c in columns]
    if len(indexes) != len(key_columns):
        return [None] * len(rows)

    keys = ["\x1f".join(str(row[i] or "") for i in indexes) for row in rows]
    placeholders = ", ".join("?" for _ in keys)
    cur = datasets.cursor(dataset_id)
    found = dict(
        cur.execute(
            f"SELECT row_key, kind FROM {TABLE} WHERE row_key IN ({placeholders})", keys
        ).fetchall()
    )
    return [found.get(key) for key in keys]


def recent_filter_sql(dataset_id: str, key_columns: list[str]) -> Optional[str]:
    """A WHERE fragment keeping only rows that arrived recently, or None.

    The filter is what a reader reviewing a delivery actually wants - scanning four
    million rows for a colour is not review. It is expressed against the arrivals table
    rather than the data, so it costs nothing when it is not asked for.
    """
    if not key_columns or not sql_utils.table_exists(dataset_id, TABLE):
        return None
    key_expr = row_identity.key_expression(key_columns)
    return f"{key_expr} IN (SELECT row_key FROM {TABLE})"
