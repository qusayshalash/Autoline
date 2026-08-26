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


class JobCancelled(Exception):
    """Raised at a checkpoint once a job's status has been moved to 'cancelling'.

    Nothing here kills the thread - DuckDB is mid-statement between checkpoints and stays
    that way until it finishes. What this buys is a stop between phases: a queued job
    never starts its first phase, and a running one stops at the next point that was
    already safe to stop at (a progress callback that fires between steps). A single long
    statement still runs to its own end.
    """


def check_cancelled(job_id: str) -> None:
    """Call from inside a running job at a point where stopping is safe - a phase
    boundary, or a progress callback that already fires periodically."""
    from app.db import catalog

    if catalog.is_cancelling(job_id):
        raise JobCancelled(job_id)
