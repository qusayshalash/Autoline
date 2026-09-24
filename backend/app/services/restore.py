"""Putting a backup back.

A backup nobody can restore is a hope, the same way a backup nobody has read back is a
hope. Taking one, verifying it and pruning it were all possible from the screen; putting
one back was a file operation somebody had to do by hand, with the server stopped. That
is not something to ask of whoever is using the app at the moment they most need it.

Four rules shape this.

**Nothing is touched until everything has been checked.** The whole backup is copied into
a staging folder first and every database in it is opened and counted against the
manifest. A backup that turns out to be unreadable halfway through fails while the live
data is still exactly where it was.

**The swap is moves, not copies.** Staging and the live data share a volume, so the
window in which the data directory is neither the old state nor the new one is a handful
of renames rather than minutes of copying. It is also the only window in which a failure
is messy, which is reason enough to make it as short as it can be.

**What is replaced is kept.** The current files are moved into `pre-restore/<timestamp>/`
rather than deleted. A restore is itself a destructive act - it is entirely possible to
restore the wrong backup - and the state it overwrote is the only copy of right now.
Nothing here ever deletes it; that is left to a person who has looked.

**The server stops answering while it happens.** A request arriving mid-swap would reopen
the catalog on a file being renamed out from under it. So the process raises a
maintenance flag that the middleware turns into 503 for every API call, and the flag
carries the stage, so the screen watching the restore learns what is happening from the
refusal itself and needs no endpoint that would have to read the database being replaced.

**What a restore restores** is worth saying plainly, because the word suggests something
narrower than the truth: the catalog file holds the accounts, the roles, the activity log
and the settings as well as the list of datasets. Restoring it takes all of them back to
the day of the backup. An account created since then will be gone. The screen says so
before anyone confirms; see `plan`.
"""

import json
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb

from app.config import settings
from app.db import catalog
from app.db.connection import datasets
from app.services import backup as backup_service

STAGING_NAME = ".restore-staging"
PRE_RESTORE_NAME = "pre-restore"

# Space to leave free after staging. Staging holds a second copy of everything for the
# length of the restore, and a disk that fills during it fails at the worst moment.
HEADROOM_BYTES = 256 * 1024 * 1024


# ---- what is happening right now ----------------------------------------------------
#
# In memory, not in the jobs table, and that is not a shortcut. The jobs table lives in
# the catalog, which is the file being replaced: a restore that wrote its own progress
# there would be writing to a database it had just closed, and the row recording that the
# restore succeeded would be overwritten by the backup's copy of that table the moment it
# did. Progress that outlives the thing it describes has to live outside it.

_lock = threading.Lock()
_state: dict = {
    "active": False,
    "stage": "",
    "name": "",
    "started_at": "",
    "finished_at": "",
    "ok": None,
    "error": "",
    "pre_restore_dir": "",
}


def status() -> dict:
    with _lock:
        return dict(_state)


def is_active() -> bool:
    with _lock:
        return bool(_state["active"])


def begin(name: str) -> None:
    """Raises the flag before the worker thread starts.

    Called from the request that asks for a restore, so that by the time it answers the
    server is already refusing everything else. Leaving it to the thread would open a gap
    - short, but exactly long enough for the screen's next poll to get a normal answer and
    conclude the restore had already finished.
    """
    _begin(name)


def _begin(name: str) -> None:
    with _lock:
        _state.update(
            active=True,
            stage="checking",
            name=name,
            started_at=_now().isoformat(timespec="seconds"),
            finished_at="",
            ok=None,
            error="",
            pre_restore_dir="",
        )


def _stage(stage: str) -> None:
    with _lock:
        _state["stage"] = stage


def _end(ok: bool, error: str = "", pre_restore_dir: str = "") -> None:
    with _lock:
        _state.update(
            active=False,
            stage="",
            finished_at=_now().isoformat(timespec="seconds"),
            ok=ok,
            error=error,
            pre_restore_dir=pre_restore_dir or _state["pre_restore_dir"],
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- reading a backup ----------------------------------------------------------------


def _find(name: str) -> Optional[dict]:
    return next((b for b in backup_service.list_all() if b["name"] == name), None)


def _dir(name: str) -> Optional[Path]:
    """The backup's folder, matched against what is on disk rather than joined onto the
    root - the same rule `backup.delete` follows, so no name out of a request can walk
    out of the backups directory."""
    root = backup_service.backups_root()
    if not root.exists():
        return None
    return next((p for p in root.iterdir() if p.is_dir() and p.name == name), None)


def _users_in(catalog_file: Path) -> Optional[int]:
    """How many accounts the backup's catalog holds. Read rather than assumed, because
    this is the number that tells somebody whether a restore will lock them out."""
    try:
        conn = duckdb.connect(str(catalog_file), read_only=True)
    except duckdb.Error:
        return None
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    except duckdb.Error:
        return None
    finally:
        conn.close()


def plan(name: str) -> dict:
    """What restoring this backup would change, and what would stop it.

    Read-only: nothing here writes, opens a live file for writing, or leaves a trace.
    It exists so that the confirmation somebody clicks is an informed one - "restore"
    on its own does not say that eleven datasets are about to disappear.
    """
    b = _find(name)
    root = _dir(name)
    if b is None or root is None:
        return {"found": False, "blockers": ["backup_not_found"], "name": name}

    by_id = {i["dataset_id"]: i for i in b["items"] if i["kind"] == "dataset"}
    current = {d["id"]: d for d in catalog.list_datasets()}

    def rows_in(item: dict) -> int:
        return int(item.get("tables", {}).get("raw_data", 0) or 0)

    restored, changed, removed = [], [], []
    for dataset_id, item in by_id.items():
        now = current.get(dataset_id)
        entry = {
            "dataset_id": dataset_id,
            "name": item.get("name") or (now or {}).get("original_filename") or dataset_id,
            "rows_in_backup": rows_in(item),
            "rows_now": int((now or {}).get("row_count_raw") or 0),
        }
        if now is None:
            restored.append(entry)
        elif entry["rows_now"] != entry["rows_in_backup"]:
            changed.append(entry)
    for dataset_id, row in current.items():
        if dataset_id not in by_id:
            removed.append(
                {
                    "dataset_id": dataset_id,
                    "name": row.get("original_filename") or dataset_id,
                    "rows_in_backup": 0,
                    "rows_now": int(row.get("row_count_raw") or 0),
                }
            )

    blockers: list[str] = []
    if not b.get("intact"):
        blockers.append("backup_not_verified")
    if is_active():
        blockers.append("restore_in_progress")
    if catalog.active_job_count() > 0:
        blockers.append("jobs_running")
    needed = int(b.get("bytes_on_disk", 0)) + HEADROOM_BYTES
    free = _free_bytes()
    if free and free < needed:
        blockers.append("not_enough_disk")

    return {
        "found": True,
        "name": name,
        "created_at": b.get("created_at", ""),
        "verified": bool(b.get("intact")),
        "include_originals": bool(b.get("include_originals")),
        "total_bytes": int(b.get("bytes_on_disk", 0)),
        "datasets_restored": restored,
        "datasets_changed": changed,
        "datasets_removed": removed,
        # the catalog is one file holding the accounts, roles, activity and settings as
        # well as the dataset list - there is no restoring part of it
        "users_now": len(catalog.list_users()),
        "users_in_backup": _users_in(root / "catalog.duckdb"),
        # restoring the signing key ends every session, including this one; not restoring
        # it would leave the backup's accounts holding tokens signed by a key they never
        # had, which is the same outcome with a worse explanation
        "ends_sessions": (root / "secret_key").exists(),
        "pre_restore_dir": str(settings.data_dir / PRE_RESTORE_NAME),
        "disk_free_bytes": free,
        "blockers": blockers,
    }


def _free_bytes() -> int:
    try:
        return shutil.disk_usage(settings.data_dir).free
    except OSError:
        return 0


# ---- doing it -------------------------------------------------------------------------


def _new_kept_dir() -> Path:
    """A folder for the state about to be replaced, which did not exist a moment ago.

    Named by the second, and two restores inside one second are ordinary in a test run
    and possible by hand. A reused name would put half of one replaced state and half of
    another in the same folder, and the note inside would describe only one of them -
    which is the worst kind of safety net, the sort that looks whole.
    """
    root = settings.data_dir / PRE_RESTORE_NAME
    base = _now().strftime(backup_service.NAME_FORMAT)
    for attempt in range(1, 1000):
        candidate = root / (base if attempt == 1 else f"{base}_{attempt}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RestoreFailed(f"could not find an unused name for {base}")


def _verify_staged(path: Path, expected: dict[str, int]) -> list[str]:
    """Opens a staged database and counts it against what the manifest said it held.

    The backup verified itself when it was written. This asks the second question: that
    the copy which just landed in staging is the same file - a bad sector, a half-finished
    copy or a truncated write between then and now all show up here, while the live data
    is still untouched.
    """
    errors: list[str] = []
    try:
        conn = duckdb.connect(str(path), read_only=True)
    except duckdb.Error as exc:
        return [f"{path.name}: cannot be opened ({exc})"]
    try:
        for table, n in expected.items():
            quoted = '"' + table.replace('"', '""') + '"'
            try:
                actual = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            except duckdb.Error as exc:
                errors.append(f"{path.name}: {table} cannot be read ({exc})")
                continue
            if actual != n:
                errors.append(f"{path.name}: {table} has {actual:,} rows, expected {n:,}")
    finally:
        conn.close()
    return errors


def run(name: str, *, actor_note: str = "") -> dict:
    """Restores one backup. Blocking; callers run it on a thread.

    Returns a result dict. Never raises for an expected failure - the caller has no
    better place to put the message than the state this already records.
    """
    started = time.perf_counter()
    b = _find(name)
    source = _dir(name)
    if b is None or source is None:
        _end(False, "backup_not_found")
        return {"ok": False, "error": "backup_not_found"}

    _begin(name)
    staging = settings.data_dir / STAGING_NAME
    # created at the swap, not here: a restore that fails while staging never replaced
    # anything, and an empty folder in pre-restore would claim otherwise
    kept: Optional[Path] = None

    try:
        # ---- stage ------------------------------------------------------------------
        _stage("staging")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        for item in b["items"]:
            src = source / item["file"]
            if not src.is_file():
                raise RestoreFailed(f"{item['file']} is missing from the backup")
            dest = staging / item["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

        _stage("verifying")
        errors: list[str] = []
        for item in b["items"]:
            if item.get("tables"):
                errors += _verify_staged(staging / item["file"], item["tables"])
        if errors:
            raise RestoreFailed("; ".join(errors)[:2000])

        # ---- swap -------------------------------------------------------------------
        #
        # From here to the end of the moves is the only window where the data directory
        # holds neither state whole. Everything in it is a rename on one volume.
        _stage("closing")
        # every open dataset, not only the ones the catalog still lists: a file whose
        # catalog row was deleted can still have a live connection, and one handle under
        # the directory is enough for the rename below to fail on Windows
        datasets.close_all()
        catalog.close()

        _stage("swapping")
        kept = _new_kept_dir()
        moved: list[tuple[Path, Path]] = []

        def put_aside(live: Path, label: str) -> None:
            if live.exists():
                target = kept / label
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(live), str(target))
                moved.append((live, target))

        try:
            put_aside(settings.catalog_path, "catalog.duckdb")
            # the write-ahead log belongs to the file it was written for; left behind it
            # would be replayed into the restored database, which is the one thing here
            # that could corrupt what was just verified
            _drop_wal(settings.catalog_path)
            # only when the backup carries one: moving the live key aside with nothing to
            # put in its place would have the next start generate a fresh key, which signs
            # out every account in the restored catalog for no reason anybody could see
            if any(i["kind"] == "key" for i in b["items"]):
                put_aside(settings.data_dir / "secret_key", "secret_key")
            put_aside(settings.datasets_dir, "datasets")
            settings.datasets_dir.mkdir(parents=True, exist_ok=True)
            if b.get("include_originals"):
                put_aside(settings.uploads_dir, "uploads")
                settings.uploads_dir.mkdir(parents=True, exist_ok=True)

            for item in b["items"]:
                src = staging / item["file"]
                dest = settings.data_dir / item["file"]
                if item["kind"] == "catalog":
                    dest = settings.catalog_path
                elif item["kind"] == "key":
                    dest = settings.data_dir / "secret_key"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
        except Exception as exc:  # noqa: BLE001
            # The swap is the one step that can leave the directory half-formed, so it is
            # the one step that undoes itself. Best effort by necessity - if moving a file
            # back also fails there is nothing left to try - but the files are all still
            # in `kept`, and the manifest written below says where.
            _stage("undoing")
            for live, target in reversed(moved):
                try:
                    if live.exists():
                        shutil.rmtree(live) if live.is_dir() else live.unlink()
                    shutil.move(str(target), str(live))
                except OSError:
                    pass
            raise RestoreFailed(f"the swap failed and was undone: {exc}") from exc

        (kept / "restored-from.json").write_text(
            json.dumps(
                {
                    "restored": name,
                    "at": _now().isoformat(timespec="seconds"),
                    "by": actor_note,
                    "note": "these are the files that were replaced; nothing deletes them",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # ---- reopen -----------------------------------------------------------------
        _stage("reopening")
        count = len(catalog.list_datasets())
        shutil.rmtree(staging, ignore_errors=True)
        _end(True, pre_restore_dir=str(kept))
        return {
            "ok": True,
            "name": name,
            "datasets": count,
            "kept_at": str(kept),
            "duration_s": round(time.perf_counter() - started, 1),
        }

    except RestoreFailed as exc:
        shutil.rmtree(staging, ignore_errors=True)
        _end(False, str(exc), pre_restore_dir=str(kept) if kept else "")
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - the state is where failures surface
        shutil.rmtree(staging, ignore_errors=True)
        _end(False, str(exc), pre_restore_dir=str(kept) if kept else "")
        return {"ok": False, "error": str(exc)}


def _drop_wal(db: Path) -> None:
    wal = db.with_suffix(db.suffix + ".wal")
    if wal.exists():
        wal.unlink()


class RestoreFailed(Exception):
    """A restore that stopped for a reason worth reading."""


# ---- what was set aside ---------------------------------------------------------------


def kept_states() -> list[dict]:
    """The states earlier restores replaced, newest first.

    Listed rather than swept, because whether the previous state is still wanted is not a
    question a cleanup rule can answer.
    """
    root = settings.data_dir / PRE_RESTORE_NAME
    if not root.exists():
        return []
    out = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        note = {}
        try:
            note = json.loads((entry / "restored-from.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        out.append(
            {
                "name": entry.name,
                "restored": note.get("restored", ""),
                "at": note.get("at", ""),
                "bytes": sum(p.stat().st_size for p in entry.rglob("*") if p.is_file()),
            }
        )
    return out


def delete_kept(name: str) -> bool:
    root = settings.data_dir / PRE_RESTORE_NAME
    if not root.exists():
        return False
    target = next((p for p in root.iterdir() if p.is_dir() and p.name == name), None)
    if target is None:
        return False
    shutil.rmtree(target)
    return True
