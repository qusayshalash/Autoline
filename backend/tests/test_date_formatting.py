"""A date is written one way, in the reader's language.

The app was showing three shapes of the same thing. A role's "updated" read
"9/13/2026, 11:03:17 PM" - the American order on an Arabic page, because
`toLocaleString()` called with no argument asks the browser what language it is in and
never asks the app. The system panel printed "2026-09-13 23:03:16" exactly as the
database held it. The activity log said "قبل ٣ دقائق", which is a different and good
thing to say, but it was the third.

Two halves again, because the fault had two. The API has to hand over an instant - a
value that says which clock it was read from - and the screen has to turn that into text
in exactly one place. `backend/app/services/clocks.py` settled the first for every
timestamp but one; `frontend/src/data/datetime.ts` is the second.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
FORMATTER = FRONTEND / "data" / "datetime.ts"


def sources() -> list[Path]:
    """Every frontend module except the one allowed to know about dates."""
    return [
        p
        for p in sorted([*FRONTEND.rglob("*.tsx"), *FRONTEND.rglob("*.ts")])
        if p != FORMATTER
    ]


def relative(path: Path) -> str:
    return path.relative_to(FRONTEND).as_posix()


def test_the_formatter_is_where_this_expects():
    assert FORMATTER.is_file(), f"no date module at {FORMATTER}"
    assert len(sources()) > 60


def test_only_the_formatter_parses_a_timestamp():
    """`new Date(x)` anywhere else is a second opinion about what the wire format means.
    Six screens each held one, and they did not agree: one appended a Z, one replaced a
    space with a T and stopped there, the rest passed the string along untouched."""
    offenders = []
    for path in sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if "new Date(" in line:
                offenders.append(f"{relative(path)}:{number}  {line.strip()[:80]}")
    assert not offenders, (
        "timestamps parsed outside data/datetime.ts:\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("call", ("toLocaleDateString", "toLocaleTimeString", "Intl.DateTimeFormat"))
def test_only_the_formatter_decides_how_a_date_looks(call):
    """These three have no use except on a date, so finding one elsewhere means a screen
    is choosing its own shape. `toLocaleString` is not listed: it is how the app formats
    numbers too, and the `new Date` check above already catches it on a date."""
    offenders = []
    for path in sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if call in line:
                offenders.append(f"{relative(path)}:{number}  {line.strip()[:80]}")
    assert not offenders, f"{call} outside data/datetime.ts:\n" + "\n".join(offenders)


# A timestamp put on the screen, rather than handed to something that formats it.
#
# The lookbehind is what separates the two. `<dd>{system.started_at}</dd>` renders the
# value; `when={arrivals.latest_at}` passes it to a component whose whole job is to
# format it, and flagging that would push callers into formatting at the call site -
# which is the scattering this module exists to stop.
RENDERED_TIMESTAMP = re.compile(r"(?<![=\w])\{\s*[\w.]*\b(\w*_at)\s*\}")


def test_no_screen_prints_a_timestamp_straight_from_the_api():
    """`<dd>{system.started_at}</dd>` on three pages. The value went out as the server's
    own wall clock and arrived as "2026-09-13 23:03:16", so that is what the reader got:
    not their language, not their timezone, not even a marker saying whose it was."""
    raw = []
    for path in FRONTEND.rglob("*.tsx"):
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for match in RENDERED_TIMESTAMP.finditer(line):
                raw.append(f"{relative(path)}:{number}  {match.group(0)}")
    assert not raw, "timestamps rendered without formatting:\n" + "\n".join(raw)


# ---- the transport half ---------------------------------------------------------------

def test_the_scan_would_notice_the_old_shape():
    """A guard on the guards: the strings they are meant to reject, rejected - and the
    ones they must not, spared."""
    assert RENDERED_TIMESTAMP.search("<dd>{system.started_at}</dd>")
    assert RENDERED_TIMESTAMP.search("<td>{u.created_at}</td>")
    # a formatted one is not a match
    assert not RENDERED_TIMESTAMP.search("<dd>{formatDateTime(system.started_at, lang)}</dd>")
    # nor is one handed to a component that formats it - the alternative would be every
    # caller formatting at the call site, which is the drift this file exists against
    assert not RENDERED_TIMESTAMP.search("<ArrivalMark when={arrivals.latest_at} />")
    assert not RENDERED_TIMESTAMP.search("title={row.created_at}")


def test_the_uptime_clock_goes_out_as_an_instant(admin):
    """The last timestamp that did not. Everything else already goes through
    clocks.iso(); this one was time.strftime over time.localtime, which produces a
    reading with no clock attached - unparseable as a moment by anything downstream."""
    body = admin.get("/api/admin/system").json()
    started = body["started_at"]

    when = datetime.fromisoformat(started.replace("Z", "+00:00"))
    assert when.tzinfo is not None, f"started_at carries no timezone: {started!r}"

    # and it is actually the truth, not merely well-formed
    age = (datetime.now(timezone.utc) - when).total_seconds()
    assert -5 < age < 86_400, f"started_at is {age}s from now: {started!r}"


def test_every_timestamp_the_api_sends_is_an_instant(admin):
    """One rule, checked across the responses that carry dates rather than on the one
    endpoint that broke it."""
    checked = 0
    for path, fields in (
        ("/api/admin/system", ("started_at",)),
        ("/api/auth/me", ("created_at", "updated_at", "last_login_at")),
    ):
        body = admin.get(path).json()
        for field in fields:
            value = body.get(field)
            if value is None:
                continue
            assert re.search(r"(Z|[+-]\d{2}:\d{2})$", value), (
                f"{path} {field} = {value!r} - no timezone, so the browser reads it as "
                "local time and shifts it by the viewer's own offset"
            )
            checked += 1
    assert checked >= 3, f"only {checked} timestamps were actually checked"
