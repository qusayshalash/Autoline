"""Reclaiming the space a dataset file keeps but no longer uses.

A DuckDB file does not shrink. Importing four million rows, then cleaning them into a
second table, then dropping and rebuilding that table, leaves the pages behind as free
space inside the file. On the dataset this project was built against that is 1.42 GB on
disk holding 348 MB of live data - three quarters of the file is nothing.

The fix is the same mechanism the backups use: `COPY FROM DATABASE` writes a fresh file
containing only what is reachable. The difference is that here the fresh file has to
replace the original, and that swap is the only genuinely dangerous operation in this
codebase - it is the one place where a mistake destroys data rather than merely
reporting it wrongly.

So the order is fixed and never varies:

  1. write the replacement beside the original, leaving the original untouched
  2. reopen the replacement and count every table against the original's counts
  3. refuse, and delete the replacement, if anything at all disagrees
  4. only then move the original aside, move the replacement in, and delete the original

At no point does the only copy of the data live in a file that has not been read back.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import duckdb

from app.db.connection import datasets
from app.services.backup import _snapshot, _table_counts

Progress = Optional[Callable[[str], None]]

# Below this, compaction is not worth a rewrite of the whole file.
MIN_WORTHWHILE_RATIO = 1.10


@dataclass
class CompactionResult:
    dataset_id: str
    bytes_before: int
    bytes_after: int
    freed_bytes: int
    tables: dict[str, int]
    duration_s: float
    skipped: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "bytes_before": self.bytes_before,
            "bytes_after": self.bytes_after,
            "freed_bytes": self.freed_bytes,
            "tables": self.tables,
            "duration_s": round(self.duration_s, 1),
            "skipped": self.skipped,
            "reason": self.reason,
        }


def estimate(dataset_id: str) -> dict:
    """How much of the file is free space, without changing anything.

    The live size is what a rewrite would produce, which is not something DuckDB reports
    directly - so it is measured the only honest way available, by asking how large the
    same content is once written out. That would mean writing the file to find out, which
    is the very thing being avoided, so instead this reports the file size and the row
    counts and leaves the judgement to the caller: a file several times larger than its
    last compacted size is the signal, and the panel shows both numbers.
    """
    path = datasets.path_for(dataset_id)
    cur = datasets.cursor(dataset_id)
    return {
        "dataset_id": dataset_id,
        "file_bytes": path.stat().st_size if path.exists() else 0,
        "tables": _table_counts(cur),
    }


def compact(dataset_id: str, *, progress: Progress = None) -> CompactionResult:
    """Rewrites the dataset file without its free space. Verifies before swapping."""

    def say(stage: str) -> None:
        if progress:
            progress(stage)

    started = time.perf_counter()
    path = datasets.path_for(dataset_id)
    if not path.exists():
        raise FileNotFoundError(f"No database file for dataset {dataset_id}")

    before = path.stat().st_size
    replacement = path.with_suffix(".compacting.duckdb")
    displaced = path.with_suffix(".old.duckdb")
    for leftover in (replacement, displaced):
        if leftover.exists():
            leftover.unlink()

    # Held for the whole operation: an import or a cleaning run starting midway through
    # would write into the file that is about to be replaced, and its work would vanish
    # with the swap.
    with datasets.write_lock(dataset_id):
        say("writing")
        expected = _snapshot(datasets.cursor(dataset_id), replacement)

        say("verifying")
        errors = _verify_against(replacement, expected)
        if errors:
            replacement.unlink(missing_ok=True)
            raise RuntimeError("compaction produced an unusable file: " + "; ".join(errors))

        after = replacement.stat().st_size
        if after >= before / MIN_WORTHWHILE_RATIO:
            # Nothing meaningful to reclaim. The original is untouched either way, so
            # this costs a temporary file and nothing else.
            replacement.unlink(missing_ok=True)
            return CompactionResult(
                dataset_id=dataset_id,
                bytes_before=before,
                bytes_after=before,
                freed_bytes=0,
                tables=expected,
                duration_s=time.perf_counter() - started,
                skipped=True,
                reason="already compact",
            )

        say("swapping")
        # The connection has to go before the file can be replaced on Windows, and the
        # pool reopens on next use.
        datasets.close(dataset_id)
        wal = path.with_suffix(path.suffix + ".wal")

        path.replace(displaced)
        try:
            replacement.replace(path)
        except OSError:
            # put the original back rather than leave the dataset without a file
            displaced.replace(path)
            raise
        if wal.exists():
            wal.unlink()
        displaced.unlink(missing_ok=True)

    say("done")
    # read through the pool again, so the result reflects a working dataset rather than
    # a file that merely exists
    final_counts = _table_counts(datasets.cursor(dataset_id))
    if final_counts != expected:
        raise RuntimeError(f"after swap the dataset reads {final_counts}, expected {expected}")

    return CompactionResult(
        dataset_id=dataset_id,
        bytes_before=before,
        bytes_after=path.stat().st_size,
        freed_bytes=before - path.stat().st_size,
        tables=expected,
        duration_s=time.perf_counter() - started,
    )


def _verify_against(path: Path, expected: dict[str, int]) -> list[str]:
    try:
        conn = duckdb.connect(str(path), read_only=True)
    except duckdb.Error as exc:
        return [f"cannot be opened ({exc})"]
    try:
        actual = _table_counts(conn)
    except duckdb.Error as exc:
        return [f"cannot be read ({exc})"]
    finally:
        conn.close()

    errors = []
    for table, n in expected.items():
        if table not in actual:
            errors.append(f"table {table} is missing")
        elif actual[table] != n:
            errors.append(f"{table} has {actual[table]:,} rows, expected {n:,}")
    for table in actual:
        if table not in expected:
            errors.append(f"unexpected table {table}")
    return errors
