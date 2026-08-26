"""Keeping the catalog's two ever-growing tables from growing forever.

`jobs` gains a row for every import, quality check, export, backup and compaction;
`cleaning_operations` gains one for every cleaning run. Neither was ever deleted from
except when the whole dataset was deleted, so on a machine that keeps its data - which
is the normal case - both only ever grew. This is the same class of problem the exports
folder had, and the same one the activity log had, arrived at the same way: something is
appended to on every operation and nothing ever removes anything.

Unlike those two, this sweep runs **on its own**, without being switched on first. That
difference is deliberate and rests on what is being deleted. Export retention deletes
files somebody asked for and may still want; the activity log is evidence, and evidence
that housekeeping quietly shortens is worth less. A settled job row is neither: it is
bookkeeping for an operation that finished weeks ago, read by nobody.

"Read by nobody" has one exception, and it is the reason this module exists instead of a
DELETE in the startup path:

    An export job row is also the record that makes its file downloadable.

`GET /datasets/{id}/export/{job_id}/download` looks the job up to learn the file's format
before serving it. Delete the row while the file is still on disk and a working download
link starts answering 404 - the file is right there and nothing can reach it. So export
jobs are pruned only once their file is already gone, which normally means export
retention removed it first. Age alone is not enough.
"""

import json
from datetime import timedelta

from app.config import settings
from app.db import admin as admin_db
from app.db import catalog
from app.services import clocks

JOBS_RETENTION_KEY = "housekeeping.jobs_retention_days"
CLEANING_RETENTION_KEY = "housekeeping.cleaning_retention_days"

# A settled job row is worth keeping while anyone might still ask what happened - long
# enough to cover "what went wrong with the import last month", and no longer.
DEFAULT_JOBS_RETENTION_DAYS = 30

# Much longer, because this is the record of what was done to the data rather than a
# note that something ran. A year outlives any question anyone is likely to ask of it.
DEFAULT_CLEANING_RETENTION_DAYS = 365

# Below this the sweep would be deleting records of things that just happened, which no
# amount of disk saving justifies. Zero is still accepted, and means off.
MIN_RETENTION_DAYS = 7


def _retention_days(key: str, default: int) -> int:
    """0 means off. Anything positive is clamped up to MIN_RETENTION_DAYS, so a value
    typed into the settings table by hand cannot turn the sweep into a shredder."""
    value = admin_db.get_setting(key, default)
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    if days <= 0:
        return 0
    return max(MIN_RETENTION_DAYS, days)


def jobs_retention_days() -> int:
    return _retention_days(JOBS_RETENTION_KEY, DEFAULT_JOBS_RETENTION_DAYS)


def cleaning_retention_days() -> int:
    return _retention_days(CLEANING_RETENTION_KEY, DEFAULT_CLEANING_RETENTION_DAYS)


def set_jobs_retention_days(days: int) -> int:
    days = 0 if int(days) <= 0 else max(MIN_RETENTION_DAYS, int(days))
    admin_db.set_setting(JOBS_RETENTION_KEY, days)
    return days


def set_cleaning_retention_days(days: int) -> int:
    days = 0 if int(days) <= 0 else max(MIN_RETENTION_DAYS, int(days))
    admin_db.set_setting(CLEANING_RETENTION_KEY, days)
    return days


def _export_file_exists(job: dict) -> bool:
    """Whether this export job still has a file behind it.

    Mirrors how download_export builds the path, deliberately: if the two ever disagree,
    the safe direction is for this one to over-report existence and keep a row that could
    have gone, never to delete a row whose file is still being served.
    """
    raw = job.get("result_json")
    fmt = "csv"
    if raw:
        try:
            fmt = json.loads(raw).get("format", "csv")
        except (TypeError, ValueError):
            # An unreadable result is not evidence the file is gone; keep the row.
            return True
    return (settings.exports_dir / job["dataset_id"] / f"{job['id']}.{fmt}").exists()


def prunable_job_ids(cutoff) -> tuple[list[str], int]:
    """(ids safe to delete, how many were held back because their file is still there)."""
    removable: list[str] = []
    held = 0
    for job in catalog.finished_jobs_before(cutoff):
        if job["kind"] == "export" and job["status"] == "done" and _export_file_exists(job):
            held += 1
            continue
        removable.append(job["id"])
    return removable, held


def sweep() -> dict:
    """One housekeeping pass. Safe to call as often as it is convenient to call: with
    nothing old enough it is two counting queries and no writes."""
    now = clocks.now()
    result = {"jobs_removed": 0, "jobs_held": 0, "cleaning_removed": 0}

    days = jobs_retention_days()
    if days > 0:
        removable, held = prunable_job_ids(now - timedelta(days=days))
        result["jobs_removed"] = catalog.delete_jobs(removable)
        result["jobs_held"] = held

    days = cleaning_retention_days()
    if days > 0:
        result["cleaning_removed"] = catalog.delete_cleaning_operations_before(
            now - timedelta(days=days)
        )

    return result


def status() -> dict:
    """What the sweep would do and what it is holding, for the settings screen."""
    now = clocks.now()
    jobs_days = jobs_retention_days()
    cleaning_days = cleaning_retention_days()

    due_jobs, held_jobs = (
        prunable_job_ids(now - timedelta(days=jobs_days)) if jobs_days > 0 else ([], 0)
    )
    due_cleaning = (
        catalog.count_cleaning_operations_before(now - timedelta(days=cleaning_days))
        if cleaning_days > 0
        else 0
    )

    return {
        "jobs_total": catalog.count_jobs(),
        "jobs_retention_days": jobs_days,
        "jobs_due": len(due_jobs),
        "jobs_held_by_exports": held_jobs,
        "cleaning_total": catalog.count_cleaning_operations(),
        "cleaning_retention_days": cleaning_days,
        "cleaning_due": due_cleaning,
    }
