"""Corrections to the data, kept apart from the data.

The uploaded file is the record. `raw_data` is rebuilt from it on every import and
`cleaned_data` is rebuilt from `raw_data` on every clean, both with `CREATE TABLE AS` -
so an edit written only into the table lives until the next import and then silently
is not there any more. That is the reason this module exists.

The rule is two-sided:

  * `corrections` is the source of truth for what a person changed. It is a separate
    table in the same dataset file, so the import's DROP does not reach it and
    compaction's whole-file copy carries it across.
  * `raw_data` is the file plus those corrections, replayed. The corrected value is
    written into the table as well, so reading stays a plain scan.

Materialising rather than joining is a deliberate cost decision: a search over the
4.1M-row registry already costs about 230ms, and a join on every query to discover that
almost no row has been corrected would be paid by every reader on every page for the
benefit of a few hundred rows. `cleaned_data` needs no replay of its own - it is built
from a `raw_data` that already carries them.

What is kept is the whole history of a cell, not just its current value: `old_value` is
what the file said, which is the thing a reader needs when deciding whether the
correction was right.
"""

from datetime import datetime
from typing import Optional

from app.db.connection import datasets
from app.services import clocks, row_identity, sql_utils

TABLE = "corrections"


class CorrectionProblem(ValueError):
    """A correction that cannot be applied, with the reason in a translatable code."""

    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def ensure_table(dataset_id: str) -> None:
    """Creates the table on first use.

    Lazily rather than at startup: dataset files are opened on demand and there can be
    hundreds of them, so a boot-time pass would open every one to add a table almost
    none of them will ever hold a row in.
    """
    cur = datasets.cursor(dataset_id)
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            row_key     VARCHAR,
            column_name VARCHAR,
            old_value   VARCHAR,
            new_value   VARCHAR,
            actor       VARCHAR,
            edited_at   TIMESTAMP,
            PRIMARY KEY (row_key, column_name)
        )
        """
    )


def _now() -> datetime:
    # naive UTC: see app/services/clocks.py for why an aware value cannot be stored here
    return clocks.now()


def find_row(dataset_id: str, key_columns: list[str], key_values: list[str]) -> Optional[dict]:
    """The single row with this key, or None.

    Returns None for "no such row" and raises for "more than one", because the two are
    different problems: the first is a stale screen, the second means the key stopped
    identifying a record - most likely because an appended batch introduced a collision -
    and correcting a cell in one of several matching rows would change data at random.
    """
    where = " AND ".join(
        f"COALESCE({sql_utils.quote_ident(c)}, '') = ?" for c in key_columns
    )
    cur = datasets.cursor(dataset_id)
    rows = cur.execute(
        f"SELECT * FROM raw_data WHERE {where} LIMIT 2", list(key_values)
    ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        raise CorrectionProblem(
            "row_not_unique",
            "More than one row has this key",
            key=key_values,
        )
    columns = [d[0] for d in cur.description]
    return dict(zip(columns, rows[0]))


def record(
    dataset_id: str,
    row_key: str,
    column: str,
    old_value: Optional[str],
    new_value: str,
    actor: str,
) -> None:
    """Remembers a correction, keeping the file's own value across repeated edits.

    `old_value` is only written the first time. Correcting a cell twice must still
    remember what the source said, not what the previous correction said - otherwise the
    original is lost after the second edit and the audit trail describes a value that
    never came from anywhere.
    """
    cur = datasets.cursor(dataset_id)
    cur.execute(
        f"""
        INSERT INTO {TABLE} (row_key, column_name, old_value, new_value, actor, edited_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (row_key, column_name) DO UPDATE SET
            new_value = excluded.new_value,
            actor     = excluded.actor,
            edited_at = excluded.edited_at
        """,
        [row_key, column, old_value, new_value, actor, _now()],
    )


def forget(dataset_id: str, row_key: str, column: str) -> Optional[dict]:
    """Removes a correction and returns it, so the caller can put the old value back."""
    cur = datasets.cursor(dataset_id)
    row = cur.execute(
        f"SELECT old_value, new_value FROM {TABLE} WHERE row_key = ? AND column_name = ?",
        [row_key, column],
    ).fetchone()
    if row is None:
        return None
    cur.execute(
        f"DELETE FROM {TABLE} WHERE row_key = ? AND column_name = ?", [row_key, column]
    )
    return {"old_value": row[0], "new_value": row[1]}


def count(dataset_id: str) -> int:
    if not sql_utils.table_exists(dataset_id, TABLE):
        return 0
    cur = datasets.cursor(dataset_id)
    return cur.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]


def listing(dataset_id: str, limit: int = 200, offset: int = 0) -> list[dict]:
    if not sql_utils.table_exists(dataset_id, TABLE):
        return []
    cur = datasets.cursor(dataset_id)
    rows = cur.execute(
        f"SELECT * FROM {TABLE} ORDER BY edited_at DESC LIMIT ? OFFSET ?", [limit, offset]
    ).fetchall()
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, r)) for r in rows]


def replay(dataset_id: str, dataset: dict) -> int:
    """Re-applies every stored correction to raw_data. Returns how many landed.

    Called after an import and after an append, which are the two operations that
    rebuild or extend the table from the file. A correction whose row is no longer
    there - the record was removed from the source - applies to nothing and is counted
    as such rather than deleted: the source may well have it again next month, and a
    correction silently discarded is a correction nobody knows they lost.

    One UPDATE per corrected column rather than per corrected cell, so a thousand
    corrections to the same column cost one pass and not a thousand.
    """
    if not sql_utils.table_exists(dataset_id, TABLE):
        return 0
    key_cols = row_identity.key_columns(dataset)
    if not key_cols:
        return 0

    # Taken here rather than left to the caller: replay writes to raw_data, and the
    # exclusive lock is reentrant, so a caller already holding it is not blocked.
    with datasets.write_lock(dataset_id):
        return _replay_locked(dataset_id, key_cols)


def _replay_locked(dataset_id: str, key_cols: list[str]) -> int:
    cur = datasets.cursor(dataset_id)
    columns = [
        r[0] for r in cur.execute(f"SELECT DISTINCT column_name FROM {TABLE}").fetchall()
    ]
    if not columns:
        return 0

    available = set(sql_utils.table_columns(dataset_id, "raw_data"))
    key_expr = row_identity.key_expression(key_cols)
    applied = 0
    for column in columns:
        if column not in available:
            continue  # the column is gone from the source; the correction waits
        quoted = sql_utils.quote_ident(column)
        cur.execute(
            f"""
            UPDATE raw_data SET {quoted} = c.new_value
            FROM {TABLE} c
            WHERE c.column_name = ? AND c.row_key = {key_expr}
            """,
            [column],
        )
        applied += cur.execute(
            f"""
            SELECT COUNT(*) FROM {TABLE} c
            WHERE c.column_name = ?
              AND EXISTS (SELECT 1 FROM raw_data WHERE {key_expr} = c.row_key)
            """,
            [column],
        ).fetchone()[0]
    return applied
