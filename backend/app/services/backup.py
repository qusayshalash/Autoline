"""Backups that are provably restorable.

Two rules shape everything here.

**A live DuckDB file must never be copied byte for byte.** The engine writes pages
continuously; a copy taken mid-write captures a torn page and the file that comes back is
corrupt - and corrupt in the worst way, because it opens fine and fails later. This is the
same hazard that made keeping the data directory inside OneDrive dangerous, so a backup
system that reintroduced it would be worse than none: it would be corruption on a
schedule, presented as safety. Instead each database is snapshotted through DuckDB itself
with COPY FROM DATABASE, which produces a consistent copy while the server keeps running.

**A backup nobody has read back is a hope, not a backup.** Every run records the row count
of every table as it snapshots, then reopens each written file and counts again. A run
that cannot be verified is reported as failed and kept, so it can be inspected, but never
counted as a good backup.
"""

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import duckdb

from app.config import settings
from app.db import catalog
from app.db.connection import datasets

MANIFEST_NAME = "manifest.json"

# Backups are named by the instant they were taken, so they sort chronologically as text
# and no counter has to be stored anywhere.
NAME_FORMAT = "%Y-%m-%d_%H%M%S"

Progress = Optional[Callable[[str], None]]


def backups_root() -> Path:
    return settings.backups_dir


def _now() -> datetime:
    return datetime.now(timezone.utc)


def same_disk_as_data() -> bool:
    """Whether the backups sit on the same physical volume as the data they protect.

    Reported rather than prevented. A same-disk copy still protects against the failures
    that actually happen most - a bad cleaning run, a deleted dataset, a corrupted write -
    but it does not survive the disk dying, and the screen should say so plainly instead
    of letting the word "backup" imply more than it delivers.
    """
    try:
        return Path(settings.data_dir).resolve().drive == backups_root().resolve().drive
    except OSError:
        return True


# ---- snapshotting ------------------------------------------------------------------


def _table_counts(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    ]
    counts = {}
    for t in tables:
        quoted = '"' + t.replace('"', '""') + '"'
        counts[t] = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
    return counts


def _snapshot(conn: duckdb.DuckDBPyConnection, dest: Path) -> dict[str, int]:
    """Writes a consistent copy of `conn`'s database to `dest` and returns what was in it.

    The alias is read from the connection rather than derived from the file name: dataset
    files are named after a generated id, and an identifier starting with a digit is not
    something to interpolate into SQL by guesswork.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    counts = _table_counts(conn)
    source = conn.execute("SELECT current_database()").fetchone()[0]
    src_ident = '"' + source.replace('"', '""') + '"'

    # ATTACH takes a literal, not a bound parameter. The path is ours - built from
    # settings and a timestamp, never from a request - and the quote doubling is here so
    # that stays true even if the configured directory ever contains one.
    literal = str(dest).replace("'", "''")
    conn.execute(f"ATTACH '{literal}' AS backup_target")
    try:
        conn.execute(f"COPY FROM DATABASE {src_ident} TO backup_target")
    finally:
        conn.execute("DETACH backup_target")
    return counts


def _verify(path: Path, expected: dict[str, int]) -> list[str]:
    """Reopens a written backup and checks it against what was snapshotted."""
    errors: list[str] = []
    try:
        conn = duckdb.connect(str(path), read_only=True)
    except duckdb.Error as exc:
        return [f"{path.name}: cannot be opened ({exc})"]
    try:
        actual = _table_counts(conn)
    except duckdb.Error as exc:
        return [f"{path.name}: cannot be read ({exc})"]
    finally:
        conn.close()

    for table, n in expected.items():
        if table not in actual:
            errors.append(f"{path.name}: table {table} is missing")
        elif actual[table] != n:
            errors.append(f"{path.name}: {table} has {actual[table]:,} rows, expected {n:,}")
    return errors


# ---- running a backup --------------------------------------------------------------


def _new_backup_dir() -> Path:
    """A directory that did not exist a moment ago.

    The name is a timestamp to the second, and two runs inside the same second are
    entirely possible on a small dataset - a duplicate name would have the second run
    write its files on top of the first, leaving one directory holding a mixture of two
    backups and a manifest describing only one of them. `exist_ok=False` makes that
    impossible rather than unlikely; the suffix keeps the name readable and still sorts
    after the unsuffixed one.
    """
    root = backups_root()
    base = _now().strftime(NAME_FORMAT)
    for attempt in range(1, 1000):
        candidate = root / (base if attempt == 1 else f"{base}_{attempt}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"could not find an unused backup name for {base}")


def run(*, include_originals: bool = False, progress: Progress = None) -> dict:
    """Takes one backup and verifies it. Returns its manifest."""

    def say(stage: str) -> None:
        if progress:
            progress(stage)

    started = time.perf_counter()
    root = _new_backup_dir()
    name = root.name

    items: list[dict] = []
    errors: list[str] = []

    say("catalog")
    catalog_dest = root / "catalog.duckdb"
    # a cursor, not the shared catalog connection: this query runs for as long as the
    # catalog takes to copy, and the rest of the app keeps reading the catalog meanwhile
    counts = _snapshot(catalog.cursor(), catalog_dest)
    errors += _verify(catalog_dest, counts)
    items.append(
        {
            "kind": "catalog",
            "file": "catalog.duckdb",
            "bytes": catalog_dest.stat().st_size,
            "tables": counts,
        }
    )

    rows = catalog.list_datasets()
    for i, row in enumerate(rows, start=1):
        dataset_id = row["id"]
        say(f"dataset:{i}/{len(rows)}")
        dest = root / "datasets" / f"{dataset_id}.duckdb"
        # under the write lock: an import or a cleaning run halfway through a table swap
        # would otherwise be snapshotted mid-swap
        with datasets.write_lock(dataset_id):
            counts = _snapshot(datasets.cursor(dataset_id), dest)
        errors += _verify(dest, counts)
        items.append(
            {
                "kind": "dataset",
                "dataset_id": dataset_id,
                "name": row.get("original_filename") or "",
                "file": f"datasets/{dataset_id}.duckdb",
                "bytes": dest.stat().st_size,
                "tables": counts,
            }
        )

    # 64 bytes, and without it every existing session is invalidated on restore. Copied
    # as a plain file because it is a plain file - nothing is writing to it.
    if settings.data_dir.joinpath("secret_key").exists():
        say("key")
        shutil.copy2(settings.data_dir / "secret_key", root / "secret_key")
        items.append({"kind": "key", "file": "secret_key", "bytes": 64, "tables": {}})

    if include_originals:
        say("originals")
        for src in sorted(settings.uploads_dir.glob("*/raw.*")):
            dest = root / "uploads" / src.parent.name / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            if dest.stat().st_size != src.stat().st_size:
                errors.append(f"{src.name}: copied size does not match the original")
            items.append(
                {
                    "kind": "original",
                    "dataset_id": src.parent.name,
                    "file": f"uploads/{src.parent.name}/{src.name}",
                    "bytes": dest.stat().st_size,
                    "tables": {},
                }
            )

    manifest = {
        "name": name,
        "created_at": _now().isoformat(timespec="seconds"),
        "duration_s": round(time.perf_counter() - started, 1),
        "include_originals": include_originals,
        "same_disk_as_data": same_disk_as_data(),
        "total_bytes": sum(i["bytes"] for i in items),
        "items": items,
        "verified": not errors,
        "errors": errors,
    }
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    say("done")
    return manifest


# ---- reading and pruning -----------------------------------------------------------


def _read_manifest(path: Path) -> Optional[dict]:
    try:
        data = json.loads((path / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # size is recomputed from disk rather than trusted: a backup that was truncated or
    # partly deleted afterwards should not keep reporting the size it had when written
    on_disk = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    data["bytes_on_disk"] = on_disk
    data["intact"] = bool(data.get("verified")) and on_disk >= data.get("total_bytes", 0)
    return data


def list_all() -> list[dict]:
    """Newest first."""
    root = backups_root()
    if not root.exists():
        return []
    out = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        manifest = _read_manifest(entry)
        if manifest is None:
            # a directory with no readable manifest is a run that died partway
            out.append(
                {
                    "name": entry.name,
                    "created_at": "",
                    "verified": False,
                    "intact": False,
                    "errors": ["incomplete: no manifest"],
                    "items": [],
                    "total_bytes": 0,
                    "bytes_on_disk": sum(
                        p.stat().st_size for p in entry.rglob("*") if p.is_file()
                    ),
                    "same_disk_as_data": same_disk_as_data(),
                    "include_originals": False,
                    "duration_s": 0,
                }
            )
        else:
            out.append(manifest)
    return out


def delete(name: str) -> bool:
    """Removes one backup. The name is matched against what is actually there rather than
    joined onto the root, so no caller can reach outside it with a crafted name."""
    root = backups_root()
    if not root.exists():
        return False
    target = next((p for p in root.iterdir() if p.is_dir() and p.name == name), None)
    if target is None:
        return False
    shutil.rmtree(target)
    return True


def prune(keep: Optional[int] = None) -> dict:
    """Keeps the newest `keep` verified backups and removes older ones.

    Unverified runs are never counted towards the number kept - otherwise a string of
    failed runs would push the last good backup out - but they are still removed once
    they are older than everything being kept, so failures do not accumulate forever.
    """
    keep = settings.backup_keep if keep is None else keep
    if keep <= 0:
        return {"removed": 0, "freed_bytes": 0}

    all_backups = list_all()
    good = [b for b in all_backups if b.get("verified")]
    survivors = {b["name"] for b in good[:keep]}

    removed = 0
    freed = 0
    for b in all_backups:
        if b["name"] in survivors:
            continue
        # keep anything newer than the oldest survivor, so a failed run sitting at the
        # top of the list is left in place to be looked at
        if survivors and b["name"] > min(survivors):
            continue
        freed += b.get("bytes_on_disk", 0)
        if delete(b["name"]):
            removed += 1
    return {"removed": removed, "freed_bytes": freed}


def summary() -> dict:
    """What the settings screen shows without listing every backup."""
    all_backups = list_all()
    good = [b for b in all_backups if b.get("verified")]
    latest = good[0] if good else None
    return {
        "backup_dir": str(backups_root()),
        "same_disk_as_data": same_disk_as_data(),
        "keep": settings.backup_keep,
        "count": len(all_backups),
        "verified_count": len(good),
        "total_bytes": sum(b.get("bytes_on_disk", 0) for b in all_backups),
        "latest_at": latest["created_at"] if latest else "",
        "latest_verified": bool(latest),
        "disk_free_bytes": _free_bytes(),
    }


def _free_bytes() -> int:
    try:
        root = backups_root()
        probe = root if root.exists() else root.parent
        return shutil.disk_usage(probe).free
    except OSError:
        return 0
