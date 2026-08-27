"""The attributes on the session cookie.

The cookie is the entire session - whoever holds it is signed in, with no password. Two
of its three protections were always on: httponly keeps script from reading it, SameSite
keeps another site from making the browser send it. The third, Secure, was hardcoded off
with a comment saying to turn it on for HTTPS, which meant it would be turned on only if
somebody remembered - and nothing about the app looks wrong while the token travels in
clear text.

So the value is derived now, and what is asserted here is mostly the derivation: that it
stays off for local http (where turning it on would stop anyone signing in at all), that
an https address turns it on without being asked, and that the combination browsers
silently reject can no longer be configured by accident.
"""

import pytest

from app.config import Settings


def _settings(**kwargs) -> Settings:
    return Settings(data_dir="./data", **kwargs)


# ---- the derivation ---------------------------------------------------------


def test_local_development_is_left_alone():
    """The reason it cannot simply default to on: over http://localhost a Secure cookie
    is discarded by the browser, and nobody can sign in."""
    assert _settings().cookie_is_secure is False


def test_an_https_address_turns_it_on_by_itself():
    """The whole point of the change - deployment day does not depend on remembering."""
    assert _settings(public_origin="https://autoline.example.com").cookie_is_secure is True


def test_a_plain_http_address_does_not():
    assert _settings(public_origin="http://autoline.example.com").cookie_is_secure is False


@pytest.mark.parametrize(
    "origin", ["  https://autoline.example.com  ", "HTTPS://Autoline.Example.COM"]
)
def test_the_address_is_read_forgivingly(origin):
    """A stray space or a capital letter in a .env file must not silently cost the
    protection - that is exactly the kind of failure nothing would report."""
    assert _settings(public_origin=origin).cookie_is_secure is True


def test_an_explicit_setting_wins_over_the_address():
    """TLS terminated by a proxy: the app only ever sees http and cannot infer it."""
    assert _settings(cookie_secure=True).cookie_is_secure is True


def test_an_explicit_setting_can_also_turn_it_off():
    assert (
        _settings(public_origin="https://x.example.com", cookie_secure=False).cookie_is_secure
        is False
    )


def test_samesite_none_forces_it_on():
    """Browsers drop a SameSite=None cookie that is not Secure, and say nothing. The
    symptom is a login that appears to succeed and leaves the user signed out."""
    assert _settings(cookie_samesite="none").cookie_is_secure is True


def test_the_default_samesite_is_unchanged():
    assert _settings().cookie_samesite == "lax"


# ---- what actually reaches the browser --------------------------------------


def _login_cookie_header(client) -> str:
    r = client.post(
        "/api/auth/login", json={"username": "test_admin", "password": "test-admin-pw"}
    )
    assert r.status_code == 200, r.text
    header = r.headers.get("set-cookie")
    assert header, "login sent no Set-Cookie"
    return header


def test_the_cookie_carries_its_other_two_protections(api):
    """These were always right. Asserted so a change to the Secure flag cannot quietly
    drop one of them on the way past."""
    header = _login_cookie_header(api).lower()
    assert "httponly" in header
    assert "samesite=lax" in header


def test_the_test_suite_runs_over_http_so_the_flag_is_off(api):
    """The suite has no PUBLIC_ORIGIN, so this is the local-development case reaching
    the browser rather than just the property in isolation."""
    assert "secure" not in _login_cookie_header(api).lower()


def test_logging_out_repeats_the_attributes(api):
    """A deletion is itself a Set-Cookie. One the browser rejects - as it does for
    SameSite=None without Secure - leaves the session cookie in place, so logging out
    would report success and change nothing."""
    header = api.post("/api/auth/logout").headers.get("set-cookie", "").lower()
    assert header, "logout sent no Set-Cookie"
    assert "httponly" in header
    assert "samesite=lax" in header
    # and it really is a deletion
    assert "expires=" in header or "max-age=0" in header


def test_signing_back_in_still_works(api):
    """The logout above ran against the session-wide client; leaving it signed out would
    break every test that follows."""
    assert _login_cookie_header(api)
    assert api.get("/api/auth/me").status_code == 200
