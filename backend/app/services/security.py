"""Password hashing, JWT issuing/verification, and first-run admin bootstrap.

Password hashing uses the stdlib's hashlib.scrypt (no C/Rust extension dependency -
avoids the Python 3.14 / Windows wheel-availability issues hit earlier with other
packages). JWTs are signed with a secret generated once and cached on disk.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from app.config import settings
from app.db import catalog

# Roles live in the database now (see db/admin.py); only the bootstrap account's role is
# referenced from code, and it is the one role that can never lose a permission.
BOOTSTRAP_ROLE = "super_admin"

ACCESS_TOKEN_TTL = timedelta(hours=12)
JWT_ALGORITHM = "HS256"

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """False for a wrong password *and* for an unreadable stored value.

    Anything other than a well-formed "salt$digest" pair is treated as a failed
    verification rather than an error: a truncated or hand-edited users row should lock
    that one account out with a 401, not turn every login attempt into a 500.
    """
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        if not salt or not expected:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(actual, expected)


# A real stored hash, generated once per process, used to spend the same effort on a
# username that does not exist as on one that does.
_DUMMY_HASH: Optional[str] = None


def dummy_verify(password: str) -> bool:
    """Always False, after doing the same work a real verification would.

    Without this, an unknown username returns in microseconds while a known one takes as
    long as scrypt does - a difference large enough to read over a network, and enough to
    let somebody enumerate which accounts exist without ever guessing a password.
    """
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_hex(16))
    verify_password(password, _DUMMY_HASH)
    return False


def _secret_key_path():
    return settings.data_dir / "secret_key"


def get_or_create_secret() -> str:
    path = _secret_key_path()
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    settings.ensure_dirs()
    key = secrets.token_hex(32)
    path.write_text(key, encoding="utf-8")
    return key


def create_access_token(user_id: str, username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, get_or_create_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, get_or_create_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def bootstrap_admin() -> None:
    """Creates the first administrator, once, on an empty installation.

    The password is generated rather than defaulted. A literal default is the same
    password on every installation of this software, and the moment the source is
    readable - which for anything on a public repository is immediately - it is a
    published credential rather than a placeholder. Rate limiting slows down guessing a
    password; it does nothing about one an attacker already knows.

    Generated once, printed once, and never recoverable from the database afterwards,
    since only its hash is stored. Set ADMIN_PASSWORD to choose your own instead.
    """
    if catalog.count_users() > 0:
        return
    username = os.environ.get("ADMIN_USERNAME", "admin")
    chosen = os.environ.get("ADMIN_PASSWORD")
    password = chosen or secrets.token_urlsafe(15)

    catalog.create_user(
        catalog.new_id(), username, hash_password(password), BOOTSTRAP_ROLE, full_name="System Administrator"
    )
    print("=" * 68)
    print(f"[bootstrap] created the first administrator: {username!r}")
    if chosen:
        print("[bootstrap] password taken from ADMIN_PASSWORD.")
    else:
        print(f"[bootstrap] generated password: {password}")
        print("[bootstrap] This is the only time it is shown - it is stored hashed.")
    print("[bootstrap] Change it after signing in.")
    print("=" * 68)
