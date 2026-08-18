"""Password hashing and session tokens.

These are the two places where a silent regression is worst: a broken hash means every
password verifies (or none do), and a broken token check means anyone holding a
hand-written cookie is an administrator. Both failure modes look like success from the
outside, so they get checked directly.
"""

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.services import security


# ---- passwords ---------------------------------------------------------------------


def test_hash_verify_round_trip():
    stored = security.hash_password("correct horse battery staple")
    assert security.verify_password("correct horse battery staple", stored) is True


def test_wrong_password_is_rejected():
    stored = security.hash_password("right")
    assert security.verify_password("wrong", stored) is False


def test_hash_is_salted_so_the_same_password_stores_differently():
    """Equal hashes for equal passwords would let anyone reading the table see which
    accounts share one."""
    a = security.hash_password("same")
    b = security.hash_password("same")
    assert a != b
    assert a.split("$")[0] != b.split("$")[0]
    # ...and both still verify
    assert security.verify_password("same", a)
    assert security.verify_password("same", b)


def test_stored_format_is_salt_and_digest_in_hex():
    stored = security.hash_password("x")
    salt_hex, digest_hex = stored.split("$")
    assert len(bytes.fromhex(salt_hex)) == 16
    assert len(bytes.fromhex(digest_hex)) == 32


@pytest.mark.parametrize("junk", ["", "nodollar", "$", "zz$zz", "deadbeef"])
def test_a_malformed_stored_hash_fails_closed(junk):
    """A truncated or garbage row must deny access, not raise - an exception here would
    surface as a 500 and, worse, might be caught somewhere as "not a rejection"."""
    assert security.verify_password("anything", junk) is False


def test_empty_password_is_not_a_wildcard():
    stored = security.hash_password("realpassword")
    assert security.verify_password("", stored) is False


def test_unicode_password_round_trips():
    """Passwords are encoded as UTF-8 before hashing; a Hebrew or Arabic passphrase must
    work, and must not collide with its own prefix."""
    stored = security.hash_password("סיסמה-كلمة-٣٢١")
    assert security.verify_password("סיסמה-كلمة-٣٢١", stored) is True
    assert security.verify_password("סיסמה-كلمة", stored) is False


# ---- tokens ------------------------------------------------------------------------


def test_token_round_trip_carries_the_identity():
    token = security.create_access_token("user-1", "amal", "editor")
    payload = security.decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["username"] == "amal"
    assert payload["role"] == "editor"


def test_token_carries_an_expiry_matching_the_configured_ttl():
    token = security.create_access_token("user-1", "amal", "editor")
    payload = security.decode_access_token(token)
    lifetime = payload["exp"] - payload["iat"]
    assert lifetime == int(security.ACCESS_TOKEN_TTL.total_seconds())


def test_a_tampered_token_is_rejected():
    """The interesting attack: keep the signature, edit the claims."""
    token = security.create_access_token("user-1", "viewer-account", "viewer")
    header, body, sig = token.split(".")
    forged = jwt.encode(
        {"sub": "user-1", "username": "viewer-account", "role": "super_admin"},
        "not-the-real-secret",
        algorithm=security.JWT_ALGORITHM,
    )
    # a token signed with any other key does not verify
    assert security.decode_access_token(forged) is None
    # nor does the original with its payload swapped for the forged one
    assert security.decode_access_token(f"{header}.{forged.split('.')[1]}.{sig}") is None


def test_an_expired_token_is_rejected():
    expired = jwt.encode(
        {
            "sub": "user-1",
            "username": "amal",
            "role": "admin",
            "iat": datetime.now(timezone.utc) - timedelta(hours=48),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        security.get_or_create_secret(),
        algorithm=security.JWT_ALGORITHM,
    )
    assert security.decode_access_token(expired) is None


def test_an_unsigned_token_is_rejected():
    """alg=none is the classic JWT bypass: a valid-looking token with no signature at
    all. It must not be accepted just because the claims parse."""
    unsigned = jwt.encode({"sub": "user-1", "role": "super_admin"}, key="", algorithm="none")
    assert security.decode_access_token(unsigned) is None


@pytest.mark.parametrize("junk", ["", "not.a.token", "a.b", "....", "null"])
def test_garbage_is_rejected_without_raising(junk):
    assert security.decode_access_token(junk) is None


def test_the_secret_is_stable_across_calls():
    """A secret regenerated per call would invalidate every live session on every
    request that happened to touch it."""
    assert security.get_or_create_secret() == security.get_or_create_secret()
    token = security.create_access_token("user-1", "amal", "admin")
    time.sleep(0.01)
    assert security.decode_access_token(token) is not None
