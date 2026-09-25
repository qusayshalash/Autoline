"""How often one caller may ask for something expensive.

This is not a defence against a distributed denial of service and nothing in an
application can be - a volumetric attack saturates the link before a line of Python runs,
and that belongs to whatever sits in front. What these cover is the smaller, likelier
problem, and the one that was measured: a search across 4.1 million rows costs about two
and a half seconds, and a signed-in account can ask for it in a loop.

The rest of the suite runs with the limiter off, because a test suite is indistinguishable
from the attack - hundreds of requests a second, one client, one address. So these switch
it on around themselves and check it against the real endpoints rather than against the
service in isolation. Every test clears the counters afterwards; a leaked bucket would
fail whatever ran next, somewhere else.
"""

import pytest
from app.config import settings
from app.services import rate_limit


@pytest.fixture
def limiting():
    """The limiter on, for one test, with no history before or after it."""
    rate_limit.clear()
    settings.rate_limit_enabled = True
    yield
    settings.rate_limit_enabled = False
    rate_limit.clear()


# ---- the bucket itself ------------------------------------------------------------------


def test_a_burst_is_allowed_and_a_stream_is_not(limiting):
    """The shape a person actually has: a handful at once while they page through a grid,
    then nothing while they read. A fixed window punishes exactly that and a token bucket
    does not, which is why it is one."""
    bucket = rate_limit.Bucket("test_burst", burst=5, per_second=1)
    assert [rate_limit.check(bucket, "someone") for _ in range(5)] == [0.0] * 5
    assert rate_limit.check(bucket, "someone") > 0


def test_the_wait_returned_is_long_enough_to_succeed(limiting):
    """It goes on the wire as Retry-After. A caller that honours it and is refused again
    would be told a number that means nothing."""
    bucket = rate_limit.Bucket("test_wait", burst=2, per_second=4)
    rate_limit.check(bucket, "someone")
    rate_limit.check(bucket, "someone")
    wait = rate_limit.check(bucket, "someone")
    assert 0 < wait <= 0.5, wait

    import time

    time.sleep(wait)
    assert rate_limit.check(bucket, "someone") == 0.0


def test_one_caller_cannot_spend_another_caller_s_allowance(limiting):
    bucket = rate_limit.Bucket("test_two", burst=2, per_second=0.1)
    assert rate_limit.check(bucket, "first") == 0.0
    assert rate_limit.check(bucket, "first") == 0.0
    assert rate_limit.check(bucket, "first") > 0
    assert rate_limit.check(bucket, "second") == 0.0


def test_the_buckets_are_kept_apart(limiting):
    """Paging through a grid must not use up the allowance for starting an export. They
    are limited for different reasons and at wildly different rates."""
    key = "someone"
    for _ in range(int(rate_limit.EXPORT.burst)):
        assert rate_limit.check(rate_limit.EXPORT, key) == 0.0
    assert rate_limit.check(rate_limit.EXPORT, key) > 0
    assert rate_limit.check(rate_limit.QUERY, key) == 0.0


def test_a_session_is_counted_apart_from_its_address(limiting):
    """Two people behind one office address are two callers, not one. Counting by address
    alone would have one person's export limit be everybody's."""
    first = rate_limit.key_for("cookie-one", "10.0.0.1")
    second = rate_limit.key_for("cookie-two", "10.0.0.1")
    assert first != second
    assert rate_limit.key_for(None, "10.0.0.1") == rate_limit.key_for(None, "10.0.0.1")


def test_the_session_token_is_not_kept_in_the_limiter(limiting):
    """It is a bearer token: whoever holds it is signed in. A limiter has no business
    keeping a copy of every live one where a diagnostic might print it."""
    token = "a.real.looking.token"
    key = rate_limit.key_for(token, None)
    assert token not in key
    assert key.startswith("s:")


def test_switching_it_off_lets_everything_through():
    """The escape hatch has to actually work: it is what the rest of the suite runs on,
    and what somebody reaches for when a limit is in their way at three in the morning."""
    rate_limit.clear()
    settings.rate_limit_enabled = False
    bucket = rate_limit.Bucket("test_off", burst=1, per_second=0.001)
    assert [rate_limit.check(bucket, "someone") for _ in range(50)] == [0.0] * 50


def test_idle_callers_are_forgotten(limiting):
    """The dictionary grows once per address that ever connects. Without a sweep that is a
    slow memory leak whose rate an attacker chooses."""
    bucket = rate_limit.Bucket("test_sweep", burst=1, per_second=1)
    for i in range(rate_limit.SWEEP_AT + 10):
        rate_limit.check(bucket, f"caller-{i}")
    assert rate_limit.snapshot()["keys"] < rate_limit.SWEEP_AT + 10


# ---- against the real endpoints ---------------------------------------------------------


def test_the_grid_refuses_a_loop_and_says_how_long_to_wait(admin, dataset, limiting):
    """The whole point, through the API: a signed-in account asking for the expensive
    thing as fast as it can is stopped, and told when to come back."""
    seen = []
    for _ in range(int(rate_limit.QUERY.burst) + 5):
        r = admin.post(f"/api/datasets/{dataset}/data", json={"page": 1, "page_size": 10})
        seen.append(r.status_code)
        if r.status_code == 429:
            assert r.json()["code"] == "too_many_requests"
            retry = r.headers.get("retry-after")
            assert retry and int(retry) >= 1, r.headers
            break
    assert 429 in seen, seen
    assert seen.count(200) >= int(rate_limit.QUERY.burst) - 1, (
        "the limit bit before the allowed burst was spent"
    )


def test_an_ordinary_amount_of_use_is_never_refused(admin, dataset, limiting):
    """A limit a real person meets is a bug, not a protection. Ten pages in a row is
    somebody scrolling, not somebody attacking."""
    for _ in range(10):
        r = admin.post(f"/api/datasets/{dataset}/data", json={"page": 1, "page_size": 50})
        assert r.status_code == 200, r.text


def test_the_cheap_endpoints_are_left_alone(admin, dataset, limiting):
    """Listing datasets costs nothing. A limit there protects nothing and is one more
    thing to meet by accident."""
    for _ in range(int(rate_limit.QUERY.burst) + 10):
        assert admin.get("/api/datasets").status_code == 200


def test_health_is_never_refused(api, limiting):
    """Whatever is watching the process must not be told to go away - and it is the one
    request that says nothing about who is asking."""
    for _ in range(int(rate_limit.GLOBAL.burst) + 20):
        assert api.get("/api/health").status_code == 200


def test_a_flood_of_logins_is_stopped_before_it_reaches_the_database(anon, limiting):
    """The finding this was built around.

    Guessing is already limited - but by writing a row to `login_attempts` for every
    failure, and the catalog is one DuckDB file behind one lock. So the guard against
    guessing was the cheapest way to put every other catalog read in the application in a
    queue, from no account at all. The address ceiling is checked in middleware, before
    anything touches the database.
    """
    codes = []
    for i in range(int(rate_limit.GLOBAL.burst) + 20):
        r = anon.post(
            "/api/auth/login", json={"username": f"flood{i}", "password": "wrong"}
        )
        codes.append(r.status_code)
        if r.status_code == 429 and r.json().get("code") == "too_many_requests":
            assert r.headers.get("retry-after")
            break
    assert 429 in codes, codes

    from app.services import login_guard

    login_guard.clear_all()
