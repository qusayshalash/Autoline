"""Rate limiting for the login endpoint.

scrypt already makes each guess expensive - roughly a tenth of a second - which stops
anyone working through a password list at speed. What it does not stop is a patient
attacker, or a script left running overnight, and neither leaves any trace: before this,
a hundred thousand failed logins and zero failed logins looked exactly the same from the
admin panel.

Three things are done about that.

**Failures are counted and the account is held off temporarily**, with the wait doubling
each time past the threshold. Temporarily, and never permanently, because a permanent
lock hands anyone who knows a username the ability to take that person's access away.

**Counting is keyed by the username that was typed, whether or not it exists.** An
attacker must not be able to tell accounts apart by how the system rate-limits them, and
a per-account counter that only exists for real accounts does exactly that. For the same
reason the endpoint spends the same effort on an unknown username as on a real one - see
`security.dummy_verify`.

**Every failure is written to the activity log.** The lockout is the smaller half of this:
what actually matters is that an attack stops being invisible.

A second counter, keyed by client address with a much higher threshold, catches the other
shape of attack - one guess each against a thousand different usernames, which no
per-account counter would ever notice.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db.catalog import _connection, _lock

# Failures allowed before a wait is imposed. Five is enough room for somebody who has
# genuinely forgotten which of their passwords this is.
USER_THRESHOLD = 5

# Per-address, this has to be far higher: a whole office behind one address is normal,
# and locking that out over one person's bad morning would be its own outage.
IP_THRESHOLD = 30

# First wait, then doubling per further failure, up to the cap.
BASE_LOCK = timedelta(minutes=1)
MAX_LOCK = timedelta(hours=1)

# A failure this old no longer counts towards the next lockout. Without decay, one
# mistyped password a month eventually locks an innocent account.
DECAY = timedelta(hours=12)


@dataclass
class Verdict:
    allowed: bool
    retry_after_s: int = 0
    failures: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seconds_until(moment: datetime, now: datetime) -> int:
    """Rounded up, never below one.

    Rounding down would be worse than useless: a client that honours Retry-After to the
    second would come back while the lock is still on and be refused again, which reads
    as the header being wrong.
    """
    return max(1, math.ceil((moment - now).total_seconds()))


def _to_db(value: datetime) -> datetime:
    """UTC, with the marker removed, which is the only form DuckDB stores faithfully.

    Handing the driver a timezone-aware datetime does not store an instant: it converts
    to the machine's local time and writes that, so a value written as 10:00 UTC comes
    back as 10:00 in a place three hours ahead. Reading it as UTC then puts every lockout
    three hours into the future - which is how a one-minute lock first measured three
    hours here.

    A clock that decides how long somebody is locked out has to be exact, so the
    conversion is done once, deliberately, at the boundary.
    """
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_aware(value) -> Optional[datetime]:
    """The inverse: values come back naive, and are UTC because `_to_db` wrote them so."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def user_key(username: str) -> str:
    # lowercased so that Admin, ADMIN and admin share one counter rather than giving an
    # attacker three budgets for the same account
    return f"user:{(username or '').strip().lower()}"


def ip_key(address: str) -> str:
    return f"ip:{address or 'unknown'}"


def _row(key: str) -> Optional[dict]:
    conn = _connection()
    with _lock:
        row = conn.execute(
            "SELECT key, failures, first_failure_at, last_failure_at, locked_until "
            "FROM login_attempts WHERE key = ?",
            [key],
        ).fetchone()
    if row is None:
        return None
    return {
        "key": row[0],
        "failures": row[1] or 0,
        "first_failure_at": _as_aware(row[2]),
        "last_failure_at": _as_aware(row[3]),
        "locked_until": _as_aware(row[4]),
    }


def _lock_duration(failures: int, threshold: int) -> Optional[timedelta]:
    if failures < threshold:
        return None
    doublings = failures - threshold
    # capped before the shift so a very large count cannot produce an enormous number
    if doublings > 20:
        return MAX_LOCK
    return min(BASE_LOCK * (2**doublings), MAX_LOCK)


def check(username: str, address: str) -> Verdict:
    """Whether this attempt may proceed, without recording anything.

    Called before the password is verified, so a locked-out caller is refused without the
    system doing the expensive hash - which is also what keeps a lockout from being a way
    to make the server work harder.
    """
    now = _now()
    for key, threshold in ((user_key(username), USER_THRESHOLD), (ip_key(address), IP_THRESHOLD)):
        row = _row(key)
        if row is None:
            continue
        until = row["locked_until"]
        if until and until > now:
            return Verdict(
                allowed=False,
                retry_after_s=_seconds_until(until, now),
                failures=row["failures"],
            )
    return Verdict(allowed=True)


def record_failure(username: str, address: str) -> Verdict:
    """Counts one failed attempt against both keys and returns the resulting state."""
    now = _now()
    worst = Verdict(allowed=True)
    for key, threshold in ((user_key(username), USER_THRESHOLD), (ip_key(address), IP_THRESHOLD)):
        row = _row(key)
        # a long-quiet key starts again from one, so old mistakes do not add to new ones
        stale = row is not None and row["last_failure_at"] and (now - row["last_failure_at"]) > DECAY
        failures = 1 if (row is None or stale) else row["failures"] + 1
        first = now if (row is None or stale) else row["first_failure_at"] or now

        duration = _lock_duration(failures, threshold)
        locked_until = now + duration if duration else None

        conn = _connection()
        with _lock:
            conn.execute(
                """
                INSERT INTO login_attempts
                    (key, failures, first_failure_at, last_failure_at, locked_until)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (key) DO UPDATE SET
                    failures = EXCLUDED.failures,
                    first_failure_at = EXCLUDED.first_failure_at,
                    last_failure_at = EXCLUDED.last_failure_at,
                    locked_until = EXCLUDED.locked_until
                """,
                [
                    key,
                    failures,
                    _to_db(first),
                    _to_db(now),
                    _to_db(locked_until) if locked_until else None,
                ],
            )

        if locked_until and not worst.retry_after_s:
            worst = Verdict(
                allowed=False,
                retry_after_s=_seconds_until(locked_until, now),
                failures=failures,
            )
        elif key.startswith("user:"):
            worst.failures = failures
    return worst


def record_success(username: str) -> None:
    """Clears the account's counter.

    Only the account's. Clearing the address counter too would let an attacker reset it
    at will by signing into an account they already own, which is the one thing that
    counter exists to prevent.
    """
    conn = _connection()
    with _lock:
        conn.execute("DELETE FROM login_attempts WHERE key = ?", [user_key(username)])


def active_lockouts() -> list[dict]:
    """Everything currently held off, for the admin panel.

    Lockouts have to be visible and clearable. A legitimate user can be locked out by
    somebody else guessing at their username, and without this that person waits with no
    explanation and nobody able to help them.
    """
    now = _now()
    conn = _connection()
    with _lock:
        rows = conn.execute(
            "SELECT key, failures, first_failure_at, last_failure_at, locked_until "
            "FROM login_attempts WHERE locked_until IS NOT NULL ORDER BY locked_until DESC"
        ).fetchall()
    out = []
    for r in rows:
        until = _as_aware(r[4])
        if not until or until <= now:
            continue
        out.append(
            {
                "key": r[0],
                "kind": "user" if r[0].startswith("user:") else "ip",
                "subject": r[0].split(":", 1)[1],
                "failures": r[1] or 0,
                "first_failure_at": _as_aware(r[2]).isoformat(timespec="seconds") if r[2] else "",
                "last_failure_at": _as_aware(r[3]).isoformat(timespec="seconds") if r[3] else "",
                "locked_until": until.isoformat(timespec="seconds"),
                "retry_after_s": _seconds_until(until, now),
            }
        )
    return out


def clear(key: str) -> bool:
    conn = _connection()
    with _lock:
        before = conn.execute(
            "SELECT COUNT(*) FROM login_attempts WHERE key = ?", [key]
        ).fetchone()[0]
        conn.execute("DELETE FROM login_attempts WHERE key = ?", [key])
    return bool(before)


def clear_all() -> int:
    conn = _connection()
    with _lock:
        n = conn.execute("SELECT COUNT(*) FROM login_attempts").fetchone()[0]
        conn.execute("DELETE FROM login_attempts")
    return n


def client_address(request) -> str:
    """The address attempts are counted against.

    Deliberately the direct peer, not X-Forwarded-For. That header is set by whoever sent
    the request unless a proxy is trusted to overwrite it, so honouring it here would let
    an attacker send a different value with every guess and never be counted at all - a
    rate limiter that an attacker can opt out of. Behind a real reverse proxy, configure
    the proxy to set the peer address instead.
    """
    return request.client.host if request.client else "unknown"
