"""One place that decides what a stored timestamp means.

DuckDB's TIMESTAMP has no timezone, and its Python driver does not store an instant:
handed a timezone-aware datetime it converts to the machine's local time and writes the
wall-clock reading. So `datetime.now(timezone.utc)` written at 21:30 UTC comes back as
00:30 in a place three hours ahead - a value that is neither UTC nor labelled as
anything else.

For a while that was invisible. The screen read those values back and rendered them as
local time, which is what a single user on a single machine wanted to see, so the two
mistakes cancelled. They stop cancelling the moment anyone in another timezone opens the
same page, or the clocks change for daylight saving, or two records written either side
of that change are compared.

The rule here is the usual one, stated once: **store UTC, transmit UTC, convert on
display.** `now()` and `to_db()` are what goes in, `iso()` is what goes out - and `iso()`
attaches the Z that lets the browser do the conversion, which `str(datetime)` does not.
"""

from datetime import datetime, timezone
from typing import Optional


def now() -> datetime:
    """The current instant, in the form DuckDB stores faithfully: UTC, no marker."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_db(value: datetime) -> datetime:
    """Any datetime, as naive UTC. An aware value is converted; a naive one is trusted
    to be UTC already, since that is the only thing this codebase writes."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def iso(value) -> Optional[str]:
    """A stored timestamp as an ISO-8601 instant, for the API.

    The trailing Z is the entire point. `str(datetime)` produces "2026-08-19 00:30:16",
    which every browser parses as *local* time - so a UTC value sent that way is
    displayed shifted by the viewer's own offset, in the wrong direction.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        return str(value)
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_naive_to_utc(value: datetime) -> datetime:
    """Reinterprets a naive datetime that holds *local* wall-clock as naive UTC.

    Only used by the one-off migration of rows written before this module existed.
    `astimezone` on a naive value treats it as local time, and does so using the offset
    that applied on that date - so timestamps from either side of a daylight-saving
    change are each corrected by their own offset rather than by today's.
    """
    return value.astimezone(timezone.utc).replace(tzinfo=None)
