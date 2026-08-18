"""A tiny background-job executor.

FastAPI's own BackgroundTasks run after the response but still block that request's
worker; for long imports/cleans/exports on multi-million-row files we want work that
survives independently of any single request and is pollable by job id. A small shared
thread pool is enough here (DuckDB releases the GIL during query execution, and file
I/O is naturally threaded), no external queue needed at this scale.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="job")


def submit(fn: Callable, *args, **kwargs) -> None:
    _executor.submit(fn, *args, **kwargs)
