"""Keeping the vehicle registry in step with the government's own copy.

The Ministry of Transport publishes the registry on data.gov.il and refreshes it almost
daily. Its "download" link sits behind a Google sign-in, so this reads the open API
instead: the same 23 columns, 32,000 vehicles a request, about 130 requests for the whole
registry.

Two steps, never one:

**Preview** pulls the whole registry into a scratch file and compares it with the
dataset - which vehicles are new, which changed and in what, which are no longer listed
- and writes the changes out as a ready batch. Nothing in the dataset is touched. If the
pull fails halfway, or the government file changes while it is being read, the preview
is thrown away and says so.

**Apply** takes that batch through the same path as any appended file: arrivals noted,
the hand corrections replayed on top, the cleaned copy rebuilt. Vehicles the registry
dropped are kept and marked (see removals.py), never deleted. Apply refuses a preview
the dataset has moved on from since, because the comparison would no longer be true.

Comparing, not reloading, is the point. Loading the full snapshot as a batch would mark
every one of four million vehicles "updated" each night; what a reader wants marked is
the few thousand that actually changed.

The government file writes three code columns without their leading zeros (1000037,
not 01000037); `PAD` puts them back, or every vehicle would look new.
"""

import http.client
import json
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from app.config import settings
from app.db import admin as admin_db
from app.db import catalog
from app.db.connection import datasets
from app.services import (
    appending,
    arrivals,
    clocks,
    corrections,
    removals,
    row_identity,
    sql_utils,
)

# ---- the source --------------------------------------------------------------------

API = "https://data.gov.il/api/3/action"
RESOURCE_ID = "053cea08-09bc-40ec-8f7a-156f0677aff3"
PAGE_SIZE = 32_000
# A generic name, nothing about who runs it: this goes to a third party with every request.
USER_AGENT = "autoline-registry-sync/1.0"
PAUSE_BETWEEN_PAGES = 0.25  # seconds; a public service, read politely
RETRIES = 4

# columns the government file writes without leading zeros, and their width in ours
PAD = {"mispar_rechev": 8, "tozeret_cd": 4, "degem_cd": 4}

# A scheduled sync applies itself only when the change is ordinary. Above this share of
# the dataset it waits for somebody to look - a renamed column, a truncated pull or a
# government-side reload all look like "everything changed".
AUTO_APPLY_MAX_SHARE = 0.20

# ---- settings ----------------------------------------------------------------------

DATASET_KEY = "registry_sync.dataset_id"
SCHEDULE_KEY = "registry_sync.schedule"  # "off" | "daily"
LAST_REPORT_KEY = "registry_sync.last_report"
LAST_SOURCE_KEY = "registry_sync.applied_source_modified"
LAST_ATTEMPT_KEY = "registry_sync.last_scheduled_day"

SCHEDULE_HOUR = 3  # local time in Israel, when nobody is working


# One sync at a time, whether started by hand or by the schedule: both write to the same
# scratch folder and the same preview.
RUN_LOCK = threading.Lock()


class SyncProblem(RuntimeError):
    """A sync that could not go ahead, with the reason as a translatable code."""

    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def work_dir() -> Path:
    return settings.data_dir / "registry_sync"


def _preview_path() -> Path:
    return work_dir() / "preview.json"


# ---- talking to data.gov.il --------------------------------------------------------

def _get(action: str, params: dict, should_cancel: Callable[[], bool] = lambda: False) -> dict:
    """One API call, retried with a growing pause; the result object or SyncProblem."""
    url = f"{API}/{action}?{urllib.parse.urlencode(params)}"
    last: Exception | None = None
    for attempt in range(RETRIES):
        if should_cancel():
            raise SyncProblem("registry_sync_cancelled", "Cancelled")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.load(response)
            if not body.get("success"):
                raise SyncProblem("registry_source_error", f"The registry answered: {body.get('error')}")
            return body["result"]
        # OSError covers the drops that arrive mid-body rather than at connect - an SSL
        # record failure, a reset - which urllib does not wrap in URLError; a long pull
        # meets one every few hundred megabytes. HTTPException covers a short read.
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(5 * (attempt + 1) ** 2)
    raise SyncProblem("registry_unreachable", f"Could not reach the government registry: {last}")


def source_info() -> dict:
    """When the government copy last changed, and how many vehicles it lists."""
    resource = _get("resource_show", {"id": RESOURCE_ID})
    count = _get("datastore_search", {"resource_id": RESOURCE_ID, "limit": 0})
    return {
        "last_modified": resource.get("last_modified") or resource.get("metadata_modified"),
        "total": int(count.get("total") or 0),
    }


def fetch_snapshot(
    destination: Path,
    progress: Callable[[str], None] = lambda _m: None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> dict:
    """Writes the whole registry to `destination` as CSV with a header. Returns the
    source info it was read against. Raises if the source changed while being read."""
    before = source_info()
    total = before["total"]
    if total <= 0:
        raise SyncProblem("registry_source_empty", "The government registry reports no vehicles")

    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding="utf-8", newline="") as out:
        for n in range(pages):
            result = _get(
                "datastore_search",
                {
                    "resource_id": RESOURCE_ID,
                    "limit": PAGE_SIZE,
                    "offset": n * PAGE_SIZE,
                    "records_format": "csv",
                    "sort": "_id asc",
                },
                should_cancel,
            )
            if n == 0:
                out.write(",".join(f["id"] for f in result["fields"]) + "\n")
            records = result.get("records") or ""
            out.write(records)
            if records and not records.endswith("\n"):
                out.write("\n")
            progress(f"fetching {n + 1}/{pages}")
            time.sleep(PAUSE_BETWEEN_PAGES)

    after = source_info()
    if after["last_modified"] != before["last_modified"]:
        raise SyncProblem(
            "registry_source_changed",
            "The government registry was updated while it was being read; try again",
        )
    return before


# ---- comparing ---------------------------------------------------------------------

def _norm(expr: str, column: str, pad: bool) -> str:
    """One cell as compared: trimmed, blank as NULL, and padded where the source drops zeros."""
    e = f"NULLIF(trim(CAST({expr} AS VARCHAR)), '')"
    if pad and column in PAD:
        e = f"lpad({e}, {PAD[column]}, '0')"
    return e


def _state_token(dataset_id: str) -> dict:
    """What the dataset looked like when a preview was taken, to refuse a stale apply."""
    row = catalog.get_dataset(dataset_id) or {}
    return {
        "row_count_raw": row.get("row_count_raw"),
        "updated_at": clocks.iso(row.get("updated_at")),
        "batches": len(appending.batch_files(dataset_id)),
        "corrections": corrections.count(dataset_id),
    }


def preview(
    dataset_id: str,
    snapshot: Optional[Path] = None,
    progress: Callable[[str], None] = lambda _m: None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> dict:
    """Pulls the registry (unless a snapshot file is given) and compares it with the
    dataset. Writes the batch and the removal lists beside preview.json; changes nothing."""
    dataset = catalog.get_dataset(dataset_id)
    if dataset is None:
        raise SyncProblem("dataset_not_found", "Dataset not found")
    key_cols = row_identity.key_columns(dataset)
    if not key_cols:
        raise SyncProblem("registry_sync_needs_key", "The dataset needs a record key to be synchronised")

    discard_preview()
    work = work_dir()
    work.mkdir(parents=True, exist_ok=True)
    source: dict = {}
    if snapshot is None:
        snapshot = work / "snapshot.csv"
        source = fetch_snapshot(snapshot, progress, should_cancel)
    progress("comparing")

    started = time.monotonic()
    try:
        summary = _compare(dataset_id, dataset, key_cols, snapshot, work, should_cancel)
    finally:
        if snapshot.parent == work and snapshot.name == "snapshot.csv":
            snapshot.unlink(missing_ok=True)
        for leftover in ("scratch.duckdb", "scratch.duckdb.wal"):
            (work / leftover).unlink(missing_ok=True)

    report = {
        "dataset_id": dataset_id,
        "created_at": clocks.iso(clocks.now()),
        "source": source,
        "state": _state_token(dataset_id),
        "compare_seconds": round(time.monotonic() - started, 1),
        **summary,
    }
    _preview_path().write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return report


def _compare(
    dataset_id: str,
    dataset: dict,
    key_cols: list[str],
    snapshot: Path,
    work: Path,
    should_cancel: Callable[[], bool],
) -> dict:
    with datasets.reading(dataset_id) as cur:
        columns = sql_utils.table_columns(dataset_id, "raw_data")
        snap_path = str(snapshot).replace("'", "''")
        header = cur.execute(
            f"SELECT * FROM read_csv('{snap_path}', header=true, all_varchar=true) LIMIT 0"
        ).description
        incoming = [d[0] for d in header if d[0] != "_id"]
        missing = [c for c in columns if c not in incoming]
        extra = [c for c in incoming if c not in columns]
        if missing or extra:
            raise SyncProblem(
                "registry_columns_differ",
                "The government registry's columns no longer match this dataset",
                missing=missing,
                extra=extra,
            )

        q = sql_utils.quote_ident
        scratch = str(work / "scratch.duckdb").replace("'", "''")
        cur.execute(f"ATTACH '{scratch}' AS sync")
        try:
            order_by = "TRY_CAST(_id AS BIGINT) DESC" if any(d[0] == "_id" for d in header) else "1"
            snap_cols = ", ".join(f"{_norm(q(c), c, True)} AS {q(c)}" for c in columns)
            key_s = row_identity.key_expression(key_cols, "s")
            key_r = row_identity.key_expression(key_cols, "r")
            # the snapshot, normalised, one row per key (the last the source lists)
            cur.execute(
                f"""
                CREATE TABLE sync.snap AS
                SELECT * EXCLUDE (_rn) FROM (
                    SELECT {snap_cols},
                           row_number() OVER (
                               PARTITION BY {row_identity.key_expression(key_cols)}
                               ORDER BY {order_by}
                           ) AS _rn
                    FROM read_csv('{snap_path}', header=true, all_varchar=true,
                                  quote='"', escape='"')
                ) WHERE _rn = 1
                """
            )
            source_rows = cur.execute(
                f"SELECT COUNT(*) FROM read_csv('{snap_path}', header=true, all_varchar=true)"
            ).fetchone()[0]
            snap_rows = cur.execute("SELECT COUNT(*) FROM sync.snap").fetchone()[0]
            if snap_rows == 0:
                raise SyncProblem("registry_source_empty", "The government registry reports no vehicles")
            if should_cancel():
                raise SyncProblem("registry_sync_cancelled", "Cancelled")

            differs = [
                f"s.{q(c)} IS DISTINCT FROM {_norm('r.' + q(c), c, False)}" for c in columns
            ]
            flags = ", ".join(f"({d}) AS d{i}" for i, d in enumerate(differs))
            cur.execute(
                f"""
                CREATE TABLE sync.changes AS
                SELECT {key_s} AS row_key,
                       CASE WHEN r._here IS NULL THEN 'new' ELSE 'changed' END AS kind,
                       {flags}
                FROM sync.snap s
                -- the marker, not the key: the key expression maps NULL to '' and so
                -- never says whether the join found a row
                LEFT JOIN (SELECT *, TRUE AS _here FROM raw_data) r ON {key_s} = {key_r}
                WHERE r._here IS NULL OR {' OR '.join(differs)}
                """
            )

            _forgive_corrected(cur, dataset_id, columns, key_cols)

            counts = dict(
                cur.execute("SELECT kind, COUNT(*) FROM sync.changes GROUP BY kind").fetchall()
            )
            per_column = cur.execute(
                "SELECT "
                + ", ".join(
                    f"COUNT(*) FILTER (WHERE kind = 'changed' AND d{i})" for i in range(len(columns))
                )
                + " FROM sync.changes"
            ).fetchone()
            changed_columns = sorted(
                ({"column": c, "count": int(n)} for c, n in zip(columns, per_column) if n),
                key=lambda item: -item["count"],
            )

            # what the registry dropped, and what came back
            have_removals = sql_utils.table_exists(dataset_id, removals.TABLE)
            already = f"AND {key_r} NOT IN (SELECT row_key FROM {removals.TABLE})" if have_removals else ""
            removed_file = work / "removed.csv"
            returned_file = work / "returned.csv"
            removed_sql = (
                f"SELECT {key_r} AS row_key FROM raw_data r "
                f"WHERE {key_r} NOT IN (SELECT {key_s} FROM sync.snap s) {already}"
            )
            cur.execute(
                f"COPY ({removed_sql}) TO '{str(removed_file).replace(chr(39), chr(39) * 2)}' "
                "(HEADER false)"
            )
            removed = _count_lines(removed_file)
            returned = 0
            if have_removals:
                cur.execute(
                    f"COPY (SELECT row_key FROM {removals.TABLE} "
                    f"WHERE row_key IN (SELECT {key_s} FROM sync.snap s)) "
                    f"TO '{str(returned_file).replace(chr(39), chr(39) * 2)}' (HEADER false)"
                )
                returned = _count_lines(returned_file)

            new_values = _new_values(cur, columns)

            # the batch itself: the changed and new rows, in the dataset's column order
            batch = work / "batch.csv"
            cols_sql = ", ".join(f"s.{q(c)}" for c in columns)
            cur.execute(
                f"""
                COPY (
                    SELECT {cols_sql} FROM sync.snap s
                    WHERE {key_s} IN (SELECT row_key FROM sync.changes)
                ) TO '{str(batch).replace(chr(39), chr(39) * 2)}'
                (HEADER false, DELIMITER ',', QUOTE '"')
                """
            )
            current_rows = cur.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0]
        finally:
            cur.execute("DETACH sync")

    return {
        "source_rows": source_rows,
        "source_duplicates": source_rows - snap_rows,
        "current_rows": current_rows,
        "new": int(counts.get("new", 0)),
        "changed": int(counts.get("changed", 0)),
        "removed": removed,
        "returned": returned,
        "changed_columns": changed_columns,
        "new_values": new_values,
    }


def _forgive_corrected(cur, dataset_id: str, columns: list[str], key_cols: list[str]) -> None:
    """Takes out of the changes what is only a hand correction disagreeing with the file.

    raw_data holds corrected values, so a corrected cell always differs from the
    registry - and every corrected vehicle would be reported changed, every night, for
    ever. For those few rows the comparison is made against the value the file had
    (the correction's old_value) instead. A correction still wins afterwards: apply
    replays every correction over whatever the batch brought.
    """
    if not sql_utils.table_exists(dataset_id, corrections.TABLE):
        return
    index = {c: i for i, c in enumerate(columns)}
    rows = cur.execute(
        f"""
        SELECT k.row_key, k.column_name, k.old_value
        FROM {corrections.TABLE} k
        JOIN sync.changes c ON c.row_key = k.row_key AND c.kind = 'changed'
        """
    ).fetchall()
    by_key: dict[str, list[tuple[str, Optional[str]]]] = {}
    for row_key, column, old in rows:
        if column in index:
            by_key.setdefault(row_key, []).append((column, old))
    q = sql_utils.quote_ident
    for row_key, fixes in by_key.items():
        snap = cur.execute(
            f"SELECT {', '.join(q(c) for c in columns)} FROM sync.snap "
            f"WHERE {row_identity.key_expression(key_cols)} = ?",
            [row_key],
        ).fetchone()
        flags = cur.execute(
            f"SELECT {', '.join(f'd{i}' for i in range(len(columns)))} FROM sync.changes WHERE row_key = ?",
            [row_key],
        ).fetchone()
        if snap is None or flags is None:
            continue
        flags = list(flags)
        for column, old in fixes:
            i = index[column]
            original = (old or "").strip() or None
            if column in PAD and original:
                original = original.rjust(PAD[column], "0")
            flags[i] = snap[i] != original
        if any(flags):
            sets = ", ".join(f"d{i} = ?" for i in range(len(columns)))
            cur.execute(f"UPDATE sync.changes SET {sets} WHERE row_key = ?", [*flags, row_key])
        else:
            cur.execute("DELETE FROM sync.changes WHERE row_key = ?", [row_key])


def _new_values(cur, columns: list[str], per_column: int = 25) -> list[dict]:
    """Hebrew values the registry now uses that the dataset has never held - a renamed
    make, a new colour - so the dictionary can be taught them before the grid shows
    them untranslated."""
    q = sql_utils.quote_ident
    out = []
    for c in columns:
        rows = cur.execute(
            f"""
            SELECT s.{q(c)} AS v, COUNT(*) AS n
            FROM sync.snap s
            WHERE regexp_matches(s.{q(c)}, '[א-ת]')
              AND s.{q(c)} NOT IN (
                  -- NULLs kept out: one NULL in a NOT IN list makes every answer NULL
                  SELECT v FROM (SELECT DISTINCT NULLIF(trim({q(c)}), '') AS v FROM raw_data)
                  WHERE v IS NOT NULL
              )
            GROUP BY v ORDER BY n DESC LIMIT {per_column}
            """
        ).fetchall()
        for value, n in rows:
            out.append({"column": c, "value": value, "count": int(n)})
    return out


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "rb") as f:
        return sum(1 for _ in f)


# ---- the current preview -----------------------------------------------------------

def current_preview() -> Optional[dict]:
    path = _preview_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def discard_preview() -> None:
    work = work_dir()
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)


# ---- applying ----------------------------------------------------------------------

def apply(
    actor: Optional[dict],
    baseline: bool,
    progress: Callable[[str], None] = lambda _m: None,
) -> dict:
    """Applies the current preview. `baseline` loads it without marking anything new or
    updated - for the first sync, which would otherwise mark most of the table."""
    report = current_preview()
    if report is None:
        raise SyncProblem("registry_no_preview", "Preview the sync before applying it")
    dataset_id = report["dataset_id"]
    dataset = catalog.get_dataset(dataset_id)
    if dataset is None:
        raise SyncProblem("dataset_not_found", "Dataset not found")
    if _state_token(dataset_id) != report["state"]:
        raise SyncProblem(
            "registry_preview_stale",
            "The dataset changed after the preview was taken; preview again",
        )

    work = work_dir()
    key_cols = row_identity.key_columns(dataset)
    columns = sql_utils.table_columns(dataset_id, "raw_data")
    now = clocks.now()
    outcome = {"incoming": 0, "replaced": 0}

    batch = work / "batch.csv"
    if batch.exists() and batch.stat().st_size > 0:
        stored = appending.next_batch_path(dataset_id)
        shutil.move(str(batch), stored)
        progress("applying")
        with datasets.write_lock(dataset_id):
            arrivals.sweep(dataset_id)
            outcome = appending._load(dataset_id, stored, columns, key_cols, mark_arrivals=not baseline)

    progress("marking")
    with datasets.write_lock(dataset_id):
        cur = datasets.cursor(dataset_id)
        removed_file = work / "removed.csv"
        returned_file = work / "returned.csv"
        if _count_lines(removed_file):
            removals.ensure_table(dataset_id)
            path = str(removed_file).replace("'", "''")
            cur.execute(
                f"""
                INSERT INTO {removals.TABLE} (row_key, removed_at)
                SELECT column0, ? FROM read_csv('{path}', header=false, all_varchar=true,
                                                columns={{'column0': 'VARCHAR'}})
                ON CONFLICT (row_key) DO NOTHING
                """,
                [now],
            )
        if _count_lines(returned_file) and sql_utils.table_exists(dataset_id, removals.TABLE):
            path = str(returned_file).replace("'", "''")
            cur.execute(
                f"""
                DELETE FROM {removals.TABLE} WHERE row_key IN (
                    SELECT column0 FROM read_csv('{path}', header=false, all_varchar=true,
                                                 columns={{'column0': 'VARCHAR'}})
                )
                """
            )

    progress("replaying corrections")
    corrections.replay(dataset_id, dataset)
    progress("rebuilding the cleaned copy")
    appending.rebuild_cleaned(dataset_id)
    total = datasets.cursor(dataset_id).execute("SELECT COUNT(*) FROM raw_data").fetchone()[0]
    catalog.update_dataset(dataset_id, row_count_raw=total)

    result = {
        "applied_at": clocks.iso(now),
        "dataset_id": dataset_id,
        "baseline": baseline,
        "new": report["new"],
        "changed": report["changed"],
        "removed": report["removed"],
        "returned": report["returned"],
        "row_count_raw": total,
        "source": report.get("source") or {},
    }
    admin_db.set_setting(LAST_REPORT_KEY, result)
    if report.get("source", {}).get("last_modified"):
        admin_db.set_setting(LAST_SOURCE_KEY, report["source"]["last_modified"])
    admin_db.log_activity(
        actor,
        "registry.synced",
        "dataset",
        dataset_id,
        dataset.get("original_filename") or "",
        f"+{report['new']} new, {report['changed']} changed, {report['removed']} removed",
        detail_code="registry_synced",
        new=report["new"],
        changed=report["changed"],
        removed=report["removed"],
    )
    discard_preview()
    return result


# ---- the schedule ------------------------------------------------------------------

def _israel_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Jerusalem"))
    except Exception:  # noqa: BLE001 - no tz database in the image: standard time is close enough
        return datetime.now(timezone.utc) + timedelta(hours=2)


def due_today() -> bool:
    """Whether the nightly sync should run now: switched on, past the hour, not yet tried today."""
    if admin_db.get_setting(SCHEDULE_KEY, "off") != "daily":
        return False
    if not admin_db.get_setting(DATASET_KEY):
        return False
    now = _israel_now()
    return now.hour >= SCHEDULE_HOUR and admin_db.get_setting(LAST_ATTEMPT_KEY) != now.date().isoformat()


def run_scheduled(progress: Callable[[str], None] = lambda _m: None) -> dict:
    """The nightly run: skip if the government copy has not changed since the last apply,
    otherwise preview, and apply only when the change is ordinary and a first sync has
    already been reviewed by somebody. Anything else is left as a preview to look at."""
    admin_db.set_setting(LAST_ATTEMPT_KEY, _israel_now().date().isoformat())
    dataset_id = admin_db.get_setting(DATASET_KEY)
    info = source_info()
    if info["last_modified"] and info["last_modified"] == admin_db.get_setting(LAST_SOURCE_KEY):
        return {"outcome": "unchanged"}
    report = preview(dataset_id, progress=progress)
    if admin_db.get_setting(LAST_REPORT_KEY) is None:
        return {"outcome": "needs_review", "reason": "first_sync"}
    touched = report["new"] + report["changed"] + report["removed"]
    if report["current_rows"] and touched / report["current_rows"] > AUTO_APPLY_MAX_SHARE:
        return {"outcome": "needs_review", "reason": "too_large"}
    apply(None, baseline=False, progress=progress)
    return {"outcome": "applied"}
