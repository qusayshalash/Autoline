"""Login rate limiting.

Two things are being protected here and they pull in opposite directions: an attacker
must be slowed down, and a real user must not be lockable out of their own account by
somebody else typing their name wrong. Most of these tests are about the seam between
those two.

The enumeration tests matter as much as the lockout ones. A rate limiter that treats a
real username differently from an invented one hands an attacker a list of who to attack.
"""

import time

import pytest
from app.services import login_guard
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def clear_counters():
    """Attempts persist in the catalog, so tests would otherwise inherit each other's."""
    login_guard.clear_all()
    yield
    login_guard.clear_all()


def attempt(username: str, password: str = "definitely-wrong"):
    return TestClient(app).post("/api/auth/login", json={"username": username, "password": password})


def fail_n(username: str, n: int):
    return [attempt(username) for _ in range(n)]


# ---- the basic contract ------------------------------------------------------------


def test_a_wrong_password_is_401_until_the_threshold(api):
    for i in range(login_guard.USER_THRESHOLD - 1):
        assert attempt("test_admin").status_code == 401, f"attempt {i + 1}"


def test_the_threshold_attempt_locks_the_account(api):
    fail_n("test_admin", login_guard.USER_THRESHOLD)
    r = attempt("test_admin")
    assert r.status_code == 429, r.text
    assert int(r.headers["Retry-After"]) > 0


def test_the_correct_password_is_refused_while_locked(api):
    """The whole point. A lockout that a correct password walks through protects nothing -
    the attacker's last guess is by definition the correct one.
    """
    fail_n("test_admin", login_guard.USER_THRESHOLD)
    r = TestClient(app).post(
        "/api/auth/login", json={"username": "test_admin", "password": "test-admin-pw"}
    )
    assert r.status_code == 429, r.text


def test_a_successful_login_clears_the_count(api):
    fail_n("test_admin", login_guard.USER_THRESHOLD - 1)

    ok = TestClient(app).post(
        "/api/auth/login", json={"username": "test_admin", "password": "test-admin-pw"}
    )
    assert ok.status_code == 200, ok.text

    # the budget is full again, so the next wrong password is an ordinary 401
    assert attempt("test_admin").status_code == 401


def test_hammering_during_a_lockout_does_not_extend_it(api):
    """Attempts made while locked are refused before they are counted.

    Deliberate, and the reason a lockout cannot be weaponised: if an attacker's own
    hammering pushed the counter up, anyone could keep a colleague locked out forever
    simply by continuing to guess. It also means the server does no hashing work for
    traffic it has already decided to refuse.
    """
    fail_n("test_admin", login_guard.USER_THRESHOLD)
    first = int(attempt("test_admin").headers["Retry-After"])
    for _ in range(20):
        attempt("test_admin")
    after = int(attempt("test_admin").headers["Retry-After"])
    assert after <= first, "twenty more guesses should not have lengthened the wait"


def test_the_wait_doubles_with_each_failure_past_the_threshold(api):
    """The ladder itself. It is only climbed across expiries - each further failure has to
    wait out the previous lock - so a long attack costs progressively more, while a real
    user's first mistake costs a minute.
    """
    waits = []
    for extra in range(4):
        login_guard.clear_all()
        for _ in range(login_guard.USER_THRESHOLD + extra):
            login_guard.record_failure("ladder-test", "1.2.3.4")
        waits.append(login_guard.check("ladder-test", "1.2.3.4").retry_after_s)

    assert waits == sorted(waits), waits
    assert waits[-1] > waits[0]
    for earlier, later in zip(waits, waits[1:]):
        assert later >= earlier * 2 - 2, f"expected doubling, got {waits}"


def test_the_wait_is_capped(api):
    """Temporary, always. An unbounded wait is a permanent lock in disguise, and hands
    anyone who knows a username the power to remove that person's access.
    """
    login_guard.clear_all()
    for _ in range(login_guard.USER_THRESHOLD + 40):
        login_guard.record_failure("cap-test", "1.2.3.4")
    assert login_guard.check("cap-test", "1.2.3.4").retry_after_s <= (
        login_guard.MAX_LOCK.total_seconds()
    )


def test_escalation_survives_waiting_out_the_first_lock(api, monkeypatch):
    """End to end: fail, wait out the lock, fail again - the second wait is longer."""
    from datetime import timedelta

    monkeypatch.setattr(login_guard, "BASE_LOCK", timedelta(seconds=1))
    fail_n("test_admin", login_guard.USER_THRESHOLD)
    first = int(attempt("test_admin").headers["Retry-After"])

    time.sleep(1.2)
    r = attempt("test_admin")           # counted now that the lock has expired
    assert r.status_code == 401
    second = int(attempt("test_admin").headers["Retry-After"])
    assert second > first


def test_a_lockout_expires_on_its_own(api, monkeypatch):
    from datetime import timedelta

    monkeypatch.setattr(login_guard, "BASE_LOCK", timedelta(seconds=1))
    fail_n("test_admin", login_guard.USER_THRESHOLD)
    assert attempt("test_admin").status_code == 429

    time.sleep(1.2)
    assert attempt("test_admin").status_code == 401, "the lock should have expired"


# ---- enumeration -------------------------------------------------------------------


def test_an_unknown_username_is_rate_limited_identically(api):
    """If only real accounts were counted, the status code alone would confirm which
    usernames exist.
    """
    fail_n("no-such-person", login_guard.USER_THRESHOLD)
    r = attempt("no-such-person")
    assert r.status_code == 429, r.text


def test_the_rejection_looks_the_same_for_real_and_invented_accounts(api):
    real = attempt("test_admin")
    fake = attempt("no-such-person")
    assert real.status_code == fake.status_code == 401
    assert real.json()["detail"] == fake.json()["detail"]


def test_a_disabled_account_is_not_distinguishable_from_a_wrong_password(admin, api):
    """"That account is disabled" is a useful message and an information leak. The account
    state belongs on the admin screen, not in a reply to an unauthenticated caller.
    """
    r = admin.post(
        "/api/users",
        json={"username": "test_disabled", "password": "test-disabled-pw", "role": "viewer"},
    )
    user_id = r.json()["id"]
    assert admin.patch(f"/api/users/{user_id}", json={"status": "inactive"}).status_code == 200

    disabled = TestClient(app).post(
        "/api/auth/login", json={"username": "test_disabled", "password": "test-disabled-pw"}
    )
    unknown = attempt("no-such-person")
    assert disabled.status_code == unknown.status_code == 401
    assert disabled.json()["detail"] == unknown.json()["detail"]


def test_case_variations_share_one_budget(api):
    """Otherwise Admin, ADMIN and admin are three separate allowances for one account."""
    for name in ["test_admin", "TEST_ADMIN", "Test_Admin", "TEST_admin", "test_ADMIN"]:
        attempt(name)
    assert attempt("test_admin").status_code == 429


def test_an_unknown_username_costs_about_as_much_time_as_a_real_one(api):
    """Guards the dummy verification. Without it an unknown username returns in
    microseconds and a real one takes as long as scrypt, which is readable over a network.
    """
    def timed(username: str) -> float:
        login_guard.clear_all()
        start = time.perf_counter()
        attempt(username)
        return time.perf_counter() - start

    real = min(timed("test_admin") for _ in range(3))
    fake = min(timed("no-such-person") for _ in range(3))
    assert fake > real * 0.5, f"unknown {fake:.4f}s vs real {real:.4f}s"


# ---- spraying ----------------------------------------------------------------------


def test_one_guess_each_against_many_usernames_is_still_caught(api):
    """The attack a per-account counter cannot see: never enough failures against any one
    name to trip it, but thousands of guesses in total from one place.
    """
    for i in range(login_guard.IP_THRESHOLD):
        attempt(f"victim-{i}")
    r = attempt("victim-fresh-name")
    assert r.status_code == 429, "the address counter should have caught the spray"


def test_signing_in_successfully_does_not_reset_the_address_counter(api):
    """Otherwise an attacker with one valid account of their own clears the address
    counter whenever they like, and it protects nothing.
    """
    for i in range(login_guard.IP_THRESHOLD - 1):
        attempt(f"sprayed-{i}")

    ok = TestClient(app).post(
        "/api/auth/login", json={"username": "test_admin", "password": "test-admin-pw"}
    )
    assert ok.status_code == 200

    attempt("sprayed-final")
    assert attempt("sprayed-another").status_code == 429


# ---- visibility and recourse -------------------------------------------------------


def test_failures_reach_the_activity_log(admin, api):
    attempt("test_admin")
    items = admin.get("/api/admin/activity", params={"page_size": 50}).json()["items"]
    assert any(i["action"] == "auth.login_failed" for i in items), \
        "a failed login must be visible to an administrator"


def test_a_lockout_is_recorded_as_well(admin, api):
    fail_n("test_admin", login_guard.USER_THRESHOLD)
    attempt("test_admin")
    items = admin.get("/api/admin/activity", params={"page_size": 50}).json()["items"]
    assert any(i["action"] == "auth.blocked" for i in items)


def test_an_admin_can_see_and_clear_a_lockout(admin, api):
    """The recourse that makes a temporary lock acceptable: somebody can lift it."""
    fail_n("test_admin", login_guard.USER_THRESHOLD)

    lockouts = admin.get("/api/admin/lockouts").json()
    mine = next(l for l in lockouts if l["subject"] == "test_admin")
    assert mine["kind"] == "user"
    assert mine["failures"] >= login_guard.USER_THRESHOLD
    assert mine["retry_after_s"] > 0

    assert admin.delete(f"/api/admin/lockouts/{mine['key']}").status_code == 200
    assert attempt("test_admin").status_code == 401, "clearing should let attempts resume"


def test_clearing_something_that_is_not_locked_is_a_404(admin):
    assert admin.delete("/api/admin/lockouts/user:nobody").status_code == 404


def test_a_viewer_cannot_see_or_clear_lockouts(viewer, api):
    assert viewer.get("/api/admin/lockouts").status_code == 403
    assert viewer.delete("/api/admin/lockouts/user:test_admin").status_code == 403


def test_expired_lockouts_are_not_listed_as_active(admin, api, monkeypatch):
    from datetime import timedelta

    monkeypatch.setattr(login_guard, "BASE_LOCK", timedelta(seconds=1))
    fail_n("test_admin", login_guard.USER_THRESHOLD)
    assert admin.get("/api/admin/lockouts").json()

    time.sleep(1.2)
    subjects = [l["subject"] for l in admin.get("/api/admin/lockouts").json()]
    assert "test_admin" not in subjects


# ---- decay -------------------------------------------------------------------------


def test_old_failures_stop_counting(api, monkeypatch):
    """One mistyped password every few months must never accumulate into a lockout."""
    from datetime import timedelta

    fail_n("test_admin", login_guard.USER_THRESHOLD - 1)
    monkeypatch.setattr(login_guard, "DECAY", timedelta(seconds=-1))  # everything is stale

    r = attempt("test_admin")
    assert r.status_code == 401, "a decayed counter should have restarted at one"
