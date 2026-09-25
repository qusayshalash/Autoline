"""How often one caller may ask for something expensive.

This is not a defence against a distributed denial of service, and nothing in an
application can be. A volumetric attack saturates the network link or the connection
table before a line of this runs; that belongs to whatever sits in front - Cloudflare,
the provider's edge - and the deployment notes say so. What this is for is the smaller,
likelier problem: one caller, from one place, asking for the expensive thing as fast as
a loop can ask for it.

That problem is real here and was measured rather than imagined. A search across 4.1
million rows takes about two and a half seconds, and a search that matches *nothing* is
the slowest of all, because the chain of OR'd patterns cannot stop early. Twenty of
those at once is the whole server. A signed-in account can do it today with a shell loop.

**The flood that needs no account is the login endpoint**, and the surprise is that the
protection against guessing is what makes it expensive: every failed attempt writes a row
to `login_attempts`, and the catalog is one DuckDB file behind one lock. So a few hundred
concurrent wrong passwords do not merely fail - they serialise every other catalog read
in the application behind them. The address bucket is checked before that write happens,
which is the point of doing this in memory.

**In memory, and therefore per process.** Behind several workers each has its own
counters and the effective limit multiplies by the number of them. That is a fair trade
for a limiter that costs a dictionary lookup instead of a database round trip, and the
numbers below are chosen loosely enough that the multiple does not matter. What would not
be a fair trade is a rate limiter that needs the database the flood is already blocking.

A token bucket rather than a fixed window: a person who pages through a grid quickly and
then reads for a minute should never see this, and a fixed window punishes exactly that
shape. The bucket refills continuously, so a burst is allowed and a sustained rate is not.

**Behind a proxy, the address has to be the real one.** Without `--proxy-headers` and
`--forwarded-allow-ips` set to the proxy, every request arrives from the proxy's address
and the whole internet shares one bucket - which turns a protection into an outage the
first time anybody is rude. The deployment notes carry this; it is set on the server
rather than here on purpose, because honouring a forwarded address from an untrusted
source is worse than ignoring it: anyone could then mint a fresh allowance per request.

The numbers were chosen against a measurement, not a feeling. This machine serves about
170 requests a second; a flood of 1500 at 50 connections was refused 1002 times and
health never once, which is the shape wanted - the ceiling well under what the server can
do, so load is shed before the server is the thing that decides.
"""

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Optional

from app.config import settings

# Keys idle for this long are dropped. Without it the dictionary grows once per address
# that ever connects, which would make the limiter its own slow memory leak - and a
# leak an attacker controls the rate of.
IDLE_SECONDS = 15 * 60

# Keys held before a sweep is considered. Swept from inside `check` rather than on a
# timer, so there is no thread to own and nothing runs when nothing is happening.
SWEEP_AT = 2048


@dataclass(frozen=True)
class Bucket:
    """How much of something may be asked for, and how fast the allowance returns.

    `burst` is what a caller may do all at once after being idle; `per_second` is what
    they may keep doing. Both are per key, and a key is one signed-in session or, when
    there is none, one address.
    """

    name: str
    burst: float
    per_second: float


# The rates. Each is set against what the thing actually costs, and against what somebody
# using the screen normally does - a limit a real user meets is a bug, not a protection.

# Reading the grid: paging, sorting, the search box. The screen debounces typing, so even
# an impatient person sends a few a second; a loop sends hundreds.
QUERY = Bucket("query", burst=40, per_second=4)

# Statistics, grouping, the value pickers. Heavier per call and asked for in smaller
# numbers - a person opens a column menu, they do not scrub through twenty of them.
ANALYSIS = Bucket("analysis", burst=20, per_second=2)

# An export writes a file and can run for minutes. Nobody legitimately starts six in a
# row, and each one that starts is disk that has to be swept up later.
EXPORT = Bucket("export", burst=4, per_second=1 / 30)

# Everything else, per address, checked before anything touches the database. This is the
# one that stands in front of the login endpoint, so it has to be generous enough for a
# whole office behind one address and still far below what a flood looks like.
GLOBAL = Bucket("global", burst=240, per_second=30)


@dataclass
class _State:
    tokens: float
    checked_at: float


_lock = threading.Lock()
# keyed by (bucket name, caller) so one caller's grid paging cannot spend their export
# allowance, and vice versa
_state: dict[tuple[str, str], _State] = {}


def key_for(session_cookie: Optional[str], address: Optional[str]) -> str:
    """Who is being counted: the session if there is one, otherwise the address.

    The cookie is hashed rather than kept. It is a bearer token - whoever holds it is
    signed in - and a limiter has no business holding a copy of every live one in a
    dictionary, least of all one that might be printed in a diagnostic.

    Counting by session and not by account is deliberate in the other direction too:
    deriving the account would mean decoding and verifying the token on every request,
    which is the work this is supposed to be cheaper than. Somebody who wants a second
    allowance can sign in twice, and signing in is what `login_guard` limits.
    """
    if session_cookie:
        return "s:" + hashlib.sha256(session_cookie.encode("utf-8")).hexdigest()[:16]
    return "a:" + (address or "unknown")


def check(bucket: Bucket, key: str, *, cost: float = 1.0) -> float:
    """Takes `cost` from this key's bucket. Returns 0 when allowed, or the seconds to
    wait when not.

    The wait returned is how long until the bucket holds enough again, which is what the
    caller puts in Retry-After. A caller told to come back in two seconds and doing so is
    behaving; one that ignores it simply keeps being refused, at the price of a dictionary
    lookup.
    """
    if not settings.rate_limit_enabled:
        return 0.0

    now = time.monotonic()
    index = (bucket.name, key)
    with _lock:
        if len(_state) >= SWEEP_AT:
            _sweep(now)
        state = _state.get(index)
        if state is None:
            state = _State(tokens=bucket.burst, checked_at=now)
            _state[index] = state
        else:
            state.tokens = min(
                bucket.burst, state.tokens + (now - state.checked_at) * bucket.per_second
            )
            state.checked_at = now

        if state.tokens >= cost:
            state.tokens -= cost
            return 0.0
        missing = cost - state.tokens
        return missing / bucket.per_second if bucket.per_second > 0 else IDLE_SECONDS


def _sweep(now: float) -> None:
    """Drops keys nobody has used lately. Called with the lock held."""
    stale = [i for i, s in _state.items() if now - s.checked_at > IDLE_SECONDS]
    for i in stale:
        del _state[i]
    # Everything is recent: the dictionary is genuinely that busy rather than leaking, and
    # dropping the coldest keys is the only way not to grow without bound. A dropped key
    # gets a full bucket back, which is the harmless direction to be wrong in - a caller
    # cold enough to be evicted from a table this size was not the one flooding.
    if len(_state) >= SWEEP_AT:
        coldest = sorted(_state, key=lambda i: _state[i].checked_at)[: SWEEP_AT // 2]
        for i in coldest:
            del _state[i]


def clear() -> None:
    """Forgets every count. For tests, and for a support case where somebody has locked
    themselves out of their own screen."""
    with _lock:
        _state.clear()


def snapshot() -> dict:
    """What the limiter is currently holding. Read by tests; nothing in the app shows it,
    because a caller must not be able to measure how close they are to the limit."""
    with _lock:
        return {
            "keys": len(_state),
            "buckets": sorted({name for name, _ in _state}),
        }
