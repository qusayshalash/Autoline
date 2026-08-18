"""One-off correction of timestamps written before the storage rule was settled.

Every timestamp in the catalog was produced by `datetime.now(timezone.utc)` and handed
to DuckDB, which quietly converted it to the machine's local time and stored that. The
rows therefore hold local wall-clock with no marker saying so. From now on
`clocks.now()` writes naive UTC instead - but the existing rows still need correcting,
once, by the offset that applied when each of them was written.

The safeguards matter more than the arithmetic here, because running this twice would
shift every timestamp a second time and there would be nothing left to detect it by:

  * it records that it has run, in the same database it corrects, and returns
    immediately if that marker is present
  * it does nothing at all on a machine already at UTC, where local and UTC agree and
    the correction would be a no-op anyway
  * it converts each value using the offset in force on that value's own date, so
    rows either side of a daylight-saving change are each corrected by their own offset
"""

from datetime import datetime, timezone

from app.services import clocks

MARKER = "migrations.timestamps_utc"

# table -> the timestamp columns in it
COLUMNS = {
    "datasets": ("created_at", "updated_at"),
    "jobs": ("created_at", "updated_at"),
    "cleaning_operations": ("created_at",),
    "users": ("created_at", "updated_at", "last_login_at"),
    "roles": ("created_at", "updated_at"),
    "activity_log": ("occurred_at",),
    "app_settings": ("updated_at",),
}


def _local_offset_seconds() -> int:
    return int(datetime.now().astimezone().utcoffset().total_seconds())


def run(conn, get_setting, set_setting) -> dict:
    """Corrects the stored timestamps. Safe to call on every start."""
    if get_setting(MARKER, None):
        return {"applied": False, "reason": "already applied"}

    if _local_offset_seconds() == 0:
        # Nothing to correct: local time is UTC, so the old writes were accidentally
        # right. Recorded as done so a later move to another timezone does not make the
        # migration think it still has work to do.
        set_setting(MARKER, {"applied_at": clocks.iso(clocks.now()), "shifted_rows": 0})
        return {"applied": False, "reason": "machine is already on UTC"}

    existing = {
        r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    }

    shifted = 0
    for table, columns in COLUMNS.items():
        if table not in existing:
            continue
        present = {r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()}
        for column in columns:
            if column not in present:
                continue
            rows = conn.execute(
                f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL"
            ).fetchall()
            for rowid, value in rows:
                if not isinstance(value, datetime):
                    continue
                corrected = clocks.local_naive_to_utc(
                    value if value.tzinfo is None else value.replace(tzinfo=None)
                )
                conn.execute(
                    f"UPDATE {table} SET {column} = ? WHERE rowid = ?", [corrected, rowid]
                )
                shifted += 1

    set_setting(MARKER, {"applied_at": clocks.iso(clocks.now()), "shifted_rows": shifted})
    return {"applied": True, "shifted_rows": shifted}
