"""DuckDB connection management.

Each dataset lives in its own DuckDB file (data/datasets/{id}.duckdb). We keep a single
long-lived read-write `duckdb.Connection` per dataset file (DuckDB allows only one
read-write handle on a file at a time), and hand out `.cursor()` copies for concurrent
reads from multiple request threads.

Access to each dataset is governed by a shared/exclusive lock:

  * **readers** - queries, statistics, exports - take it shared, so any number of them
    run at once, which is the whole point of handing out cursors.
  * **writers** - imports, cleaning, compaction, deletion - take it exclusively, so no
    reader is part-way through when the table underneath it is swapped or the file it is
    reading is replaced.

Reading used to take nothing at all. That was survivable while every writer wrote
*through* the connection, because DuckDB's own transactions covered it. Compaction broke
that assumption: it replaces the file and has to close the connection to do so on
Windows, and closing a connection while an export is streaming four million rows out of
it fails the export with an error about a closed database. Exports take minutes, so the
window is not theoretical.

The lock is per dataset id and outlives the connection, which matters more than it
sounds: the old code stored the write lock beside the connection and dropped both when
closing, so a writer that closed the connection while holding the lock left the next
writer to create a *fresh* lock and acquire it immediately - two writers at once, on the
one path where that must never happen.
"""

import threading
from functools import wraps
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from app.config import settings


class _RWLock:
    """Shared for readers, exclusive for writers, with writers given priority.

    Writer priority is deliberate: a steady trickle of read requests - which is what a
    dashboard polling every few seconds looks like - would otherwise postpone a pending
    import indefinitely, and the import is the thing somebody is waiting on.

    The exclusive side is reentrant for the thread already holding it, because the
    operations that need it are built from smaller ones that also need it: compaction
    holds the lock for the whole swap and calls `close()` in the middle of it.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        # per-thread read depth, so a reader that takes the lock again does not queue
        # behind a waiting writer that is itself waiting for that reader to finish
        self._reader_depth: dict[int, int] = {}
        self._writer: int | None = None
        self._depth = 0
        self._waiting_writers = 0

    @contextmanager
    def shared(self) -> Iterator[None]:
        me = threading.get_ident()
        with self._cond:
            if self._writer == me:
                # the writer may read whatever it likes; it already excludes everyone
                counted = False
            elif me in self._reader_depth:
                # A reader taking the lock again goes straight through. Making it queue
                # behind a waiting writer would be waiting for itself - that writer
                # cannot start until this very thread's outer read finishes. Reads nest
                # routinely here, because the query helpers are built from each other.
                self._reader_depth[me] += 1
                counted = True
            else:
                while self._writer is not None or self._waiting_writers > 0:
                    self._cond.wait()
                self._readers += 1
                self._reader_depth[me] = 1
                counted = True
        try:
            yield
        finally:
            if counted:
                with self._cond:
                    depth = self._reader_depth[me] - 1
                    if depth:
                        self._reader_depth[me] = depth
                    else:
                        del self._reader_depth[me]
                        self._readers -= 1
                        if self._readers == 0:
                            self._cond.notify_all()

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        me = threading.get_ident()
        with self._cond:
            if self._writer == me:
                self._depth += 1
            else:
                self._waiting_writers += 1
                try:
                    while self._writer is not None or self._readers > 0:
                        self._cond.wait()
                finally:
                    self._waiting_writers -= 1
                self._writer = me
                self._depth = 1
        try:
            yield
        finally:
            with self._cond:
                self._depth -= 1
                if self._depth == 0:
                    self._writer = None
                    self._cond.notify_all()


class _DatasetConnections:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, duckdb.DuckDBPyConnection] = {}
        # keyed by dataset id and never removed: a lock that outlives the connection is
        # the only kind that can protect the act of closing it
        self._locks: dict[str, _RWLock] = {}

    def _path_for(self, dataset_id: str) -> Path:
        return settings.datasets_dir / f"{dataset_id}.duckdb"

    def _lock_for(self, dataset_id: str) -> _RWLock:
        with self._lock:
            lock = self._locks.get(dataset_id)
            if lock is None:
                lock = _RWLock()
                self._locks[dataset_id] = lock
            return lock

    def _get_or_open(self, dataset_id: str) -> duckdb.DuckDBPyConnection:
        with self._lock:
            conn = self._connections.get(dataset_id)
            if conn is None:
                settings.ensure_dirs()
                conn = duckdb.connect(str(self._path_for(dataset_id)))
                self._connections[dataset_id] = conn
            return conn

    def cursor(self, dataset_id: str) -> duckdb.DuckDBPyConnection:
        """A thread-local cursor for read queries.

        Takes no lock on its own. Callers that hold a cursor across more than a single
        statement - which is every caller that matters - should be inside `reading()`,
        which is what keeps the connection alive for the duration.
        """
        return self._get_or_open(dataset_id).cursor()

    @contextmanager
    def reading(self, dataset_id: str) -> Iterator[duckdb.DuckDBPyConnection]:
        """A cursor, with the dataset held open for as long as it is in use."""
        with self._lock_for(dataset_id).shared():
            yield self.cursor(dataset_id)

    def write_lock(self, dataset_id: str):
        """Exclusive access. Used as `with datasets.write_lock(id):`."""
        return self._lock_for(dataset_id).exclusive()

    def close(self, dataset_id: str) -> None:
        """Closes the connection, waiting for readers to finish first."""
        with self._lock_for(dataset_id).exclusive():
            with self._lock:
                conn = self._connections.pop(dataset_id, None)
            if conn is not None:
                conn.close()

    def dataset_file_size(self, dataset_id: str) -> int:
        path = self._path_for(dataset_id)
        return path.stat().st_size if path.exists() else 0

    def path_for(self, dataset_id: str) -> Path:
        """The file backing this dataset. Public so maintenance work - compaction, and
        anything else that has to replace the file rather than write through it - can
        reach it without reaching into a private helper."""
        return self._path_for(dataset_id)

    def delete(self, dataset_id: str) -> None:
        with self._lock_for(dataset_id).exclusive():
            self.close(dataset_id)
            path = self._path_for(dataset_id)
            if path.exists():
                path.unlink()
            wal = path.with_suffix(path.suffix + ".wal")
            if wal.exists():
                wal.unlink()


datasets = _DatasetConnections()


def read_locked(fn):
    """Holds the dataset's shared lock for the whole call.

    Applied to the read entry points rather than to every `cursor()` call inside them,
    because what has to be protected is the span a cursor is used over, not the moment it
    is handed out. The shared lock nests, so helpers that are themselves decorated - and
    several are - cost nothing extra when called from inside one.

    Every decorated function takes the dataset id first, which is the convention
    throughout the service layer.
    """

    @wraps(fn)
    def wrapper(dataset_id: str, *args, **kwargs):
        with datasets._lock_for(dataset_id).shared():
            return fn(dataset_id, *args, **kwargs)

    return wrapper
