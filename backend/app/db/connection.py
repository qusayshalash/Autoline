"""DuckDB connection management.

Each dataset lives in its own DuckDB file (data/datasets/{id}.duckdb). We keep a single
long-lived read-write `duckdb.Connection` per dataset file (DuckDB allows only one
read-write handle on a file at a time), and hand out `.cursor()` copies for concurrent
reads from multiple request threads. Writes (imports, cleaning) are serialized with a
per-dataset lock so two mutations never race and readers never observe a half-finished
table swap.
"""

import threading
from pathlib import Path

import duckdb

from app.config import settings


class _DatasetConnections:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, duckdb.DuckDBPyConnection] = {}
        self._write_locks: dict[str, threading.Lock] = {}

    def _path_for(self, dataset_id: str) -> Path:
        return settings.datasets_dir / f"{dataset_id}.duckdb"

    def _get_or_open(self, dataset_id: str) -> duckdb.DuckDBPyConnection:
        with self._lock:
            conn = self._connections.get(dataset_id)
            if conn is None:
                settings.ensure_dirs()
                conn = duckdb.connect(str(self._path_for(dataset_id)))
                self._connections[dataset_id] = conn
                self._write_locks[dataset_id] = threading.Lock()
            return conn

    def cursor(self, dataset_id: str) -> duckdb.DuckDBPyConnection:
        """A thread-local cursor for read queries. Safe to use concurrently across requests."""
        return self._get_or_open(dataset_id).cursor()

    def write_lock(self, dataset_id: str) -> threading.Lock:
        self._get_or_open(dataset_id)
        return self._write_locks[dataset_id]

    def close(self, dataset_id: str) -> None:
        with self._lock:
            conn = self._connections.pop(dataset_id, None)
            self._write_locks.pop(dataset_id, None)
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
        self.close(dataset_id)
        path = self._path_for(dataset_id)
        if path.exists():
            path.unlink()
        wal = path.with_suffix(path.suffix + ".wal")
        if wal.exists():
            wal.unlink()


datasets = _DatasetConnections()
