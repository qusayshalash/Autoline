"""What is on disk, what it is for, and what is safe to remove.

The data directory grows in three different ways and only one of them is bounded:

  * `datasets/*.duckdb` is the database. Never removable - deleting it deletes the data.
  * `uploads/<id>/raw.*` is the original upload. Never removed here either: it is the
    only copy of what the user actually gave us, and the quality report reads it.
  * `uploads/<id>/normalized.csv` and `cleaned.csv` are intermediates. The first is read
    once during import; the second is written by every cleaning run purely to measure
    its own size. Neither is ever read again, and both are regenerated on demand.
  * `exports/<id>/*` accumulates one file per export, forever.

`settings.export_ttl_hours` has existed since the first version and was never applied,
which is how the exports folder reached 2.8 GB. Retention lives here now - but it is
opt-in, and every deletion path can be previewed before it runs.
"""

import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.config import settings
from app.db import admin as admin_db

# Files inside uploads/<id>/ that are safe to delete: derived, never read after import,
# and rebuilt automatically. Anything not listed here - notably raw.* - is protected.
REMOVABLE_INTERMEDIATES = ("normalized.csv", "cleaned.csv")

RETENTION_KEY = "storage.export_retention_hours"

# Retention is OFF until someone turns it on. `settings.export_ttl_hours` is the value
# offered as a starting point in the UI, not a default that acts on its own: deleting
# files is not something a piece of housekeeping should decide to do the first time it
# runs, on data the owner has never been asked about.
DEFAULT_RETENTION_HOURS = 0
SUGGESTED_RETENTION_HOURS = settings.export_ttl_hours


@dataclass
class Candidate:
    path: Path
    category: str
    bytes: int
    modified: datetime
    age_hours: float
    reason: str

    def as_dict(self, root: Path) -> dict:
        return {
            "path": str(self.path.relative_to(root)).replace("\\", "/"),
            "category": self.category,
            "bytes": self.bytes,
            "modified": self.modified.isoformat(timespec="seconds"),
            "age_hours": round(self.age_hours, 1),
            "reason": self.reason,
        }


def retention_hours() -> int:
    value = admin_db.get_setting(RETENTION_KEY, DEFAULT_RETENTION_HOURS)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_HOURS


def set_retention_hours(hours: int) -> int:
    hours = max(0, int(hours))
    admin_db.set_setting(RETENTION_KEY, hours)
    return hours


def _dir_size(path: Path) -> tuple[int, int]:
    """(bytes, file count) for a directory tree, tolerant of files vanishing mid-walk."""
    total = 0
    count = 0
    if not path.exists():
        return 0, 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
                count += 1
        except OSError:
            continue
    return total, count


def _stat(path: Path) -> tuple[int, datetime, float]:
    st = path.stat()
    modified = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    age = (time.time() - st.st_mtime) / 3600
    return st.st_size, modified, age


def breakdown() -> dict:
    """Every category with its size, and how much of it is currently reclaimable."""
    uploads_bytes, uploads_files = _dir_size(settings.uploads_dir)
    datasets_bytes, datasets_files = _dir_size(settings.datasets_dir)
    exports_bytes, exports_files = _dir_size(settings.exports_dir)

    originals = 0
    intermediates = 0
    for entry in _iter_uploads():
        size = entry[1]
        if entry[0].name.startswith("raw."):
            originals += size
        elif entry[0].name in REMOVABLE_INTERMEDIATES:
            intermediates += size

    reclaimable = plan()
    catalog_bytes = settings.catalog_path.stat().st_size if settings.catalog_path.exists() else 0

    return {
        "data_dir": str(settings.data_dir),
        "total_bytes": uploads_bytes + datasets_bytes + exports_bytes + catalog_bytes,
        "retention_hours": retention_hours(),
        "suggested_retention_hours": SUGGESTED_RETENTION_HOURS,
        "categories": [
            {
                "key": "datasets",
                "bytes": datasets_bytes,
                "files": datasets_files,
                "removable": False,
            },
            {
                "key": "originals",
                "bytes": originals,
                "files": sum(1 for p, _ in _iter_uploads() if p.name.startswith("raw.")),
                "removable": False,
            },
            {
                "key": "intermediates",
                "bytes": intermediates,
                "files": sum(1 for p, _ in _iter_uploads() if p.name in REMOVABLE_INTERMEDIATES),
                "removable": True,
            },
            {
                "key": "exports",
                "bytes": exports_bytes,
                "files": exports_files,
                "removable": True,
            },
            {
                "key": "catalog",
                "bytes": catalog_bytes,
                "files": 1 if catalog_bytes else 0,
                "removable": False,
            },
        ],
        "reclaimable_bytes": sum(c.bytes for c in reclaimable),
        "reclaimable_files": len(reclaimable),
        "uploads_bytes": uploads_bytes,
    }


def _iter_uploads() -> Iterable[tuple[Path, int]]:
    if not settings.uploads_dir.exists():
        return
    for p in settings.uploads_dir.rglob("*"):
        try:
            if p.is_file():
                yield p, p.stat().st_size
        except OSError:
            continue


def plan(
    *, expired_exports: bool = True, all_exports: bool = False, intermediates: bool = True
) -> list[Candidate]:
    """What a cleanup would delete, without deleting anything.

    The UI calls this first and shows the list, because "free up space" should never be
    a button whose effect you discover afterwards.
    """
    hours = retention_hours()
    out: list[Candidate] = []

    if settings.exports_dir.exists() and (all_exports or (expired_exports and hours > 0)):
        for p in settings.exports_dir.rglob("*"):
            try:
                if not p.is_file():
                    continue
                size, modified, age = _stat(p)
            except OSError:
                continue
            if all_exports:
                out.append(Candidate(p, "exports", size, modified, age, "all_exports"))
            elif age >= hours:
                out.append(Candidate(p, "exports", size, modified, age, "expired"))

    if intermediates:
        for p, _ in _iter_uploads():
            if p.name not in REMOVABLE_INTERMEDIATES:
                continue
            try:
                size, modified, age = _stat(p)
            except OSError:
                continue
            out.append(Candidate(p, "intermediates", size, modified, age, "regenerable"))

    out.sort(key=lambda c: c.bytes, reverse=True)
    return out


def _is_protected(path: Path) -> bool:
    """Belt and braces: nothing outside the data directory, and never an original or a
    database, whatever the caller asked for."""
    try:
        path.relative_to(settings.data_dir)
    except ValueError:
        return True
    if path.suffix in (".duckdb", ".wal"):
        return True
    if path.name.startswith("raw."):
        return True
    return False


def cleanup(
    *, expired_exports: bool = True, all_exports: bool = False, intermediates: bool = True
) -> dict:
    """Deletes what `plan` listed and reports what actually went."""
    candidates = plan(
        expired_exports=expired_exports, all_exports=all_exports, intermediates=intermediates
    )
    freed = 0
    removed = 0
    failed: list[str] = []
    for c in candidates:
        if _is_protected(c.path):
            continue
        try:
            c.path.unlink()
            freed += c.bytes
            removed += 1
        except OSError as exc:
            failed.append(f"{c.path.name}: {exc}")

    _prune_empty_dirs(settings.exports_dir)

    return {"removed_files": removed, "freed_bytes": freed, "failed": failed}


def _prune_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for p in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        try:
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except OSError:
            continue


def sweep_expired_exports() -> dict:
    """Retention sweep at startup. Does nothing at all unless a retention period has
    been configured, so an untouched installation never deletes anything by itself."""
    if retention_hours() <= 0:
        return {"removed_files": 0, "freed_bytes": 0, "failed": []}
    return cleanup(expired_exports=True, all_exports=False, intermediates=False)


def disk_free_bytes() -> int:
    try:
        return shutil.disk_usage(settings.data_dir).free
    except OSError:
        return 0
