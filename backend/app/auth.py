"""FastAPI auth dependencies: current-user resolution from the session cookie, and
permission checks built on top of it.

Access is decided by permission, not by role name. A role is just a named bundle of
permissions stored in the database, so a custom role works exactly like a built-in one
and no endpoint needs to know which roles exist.
"""

from fastapi import Depends, HTTPException, Request

from app.db import admin as admin_db
from app.db import catalog
from app.services import security

COOKIE_NAME = "access_token"


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Not authenticated")
    payload = security.decode_access_token(token)
    if payload is None:
        raise HTTPException(401, "Invalid or expired session")
    user = catalog.get_user_by_id(payload["sub"])
    if user is None:
        raise HTTPException(401, "Account no longer active")
    # status is the source of truth; anything but "active" cannot hold a session
    if (user.get("status") or ("active" if user.get("is_active") else "inactive")) != "active":
        raise HTTPException(401, "Account no longer active")
    # resolved per request so a permission change takes effect immediately, without
    # waiting for the token to expire
    user["permissions"] = admin_db.permissions_for_role(user["role"])
    return user


def require_permission(*keys: str):
    """Requires every listed permission. Use one key per endpoint in almost all cases."""

    def _check(user: dict = Depends(get_current_user)) -> dict:
        granted = set(user.get("permissions") or [])
        missing = [k for k in keys if k not in granted]
        if missing:
            raise HTTPException(403, "You do not have permission to perform this action")
        return user

    return _check


def require_any_permission(*keys: str):
    """Requires at least one of the listed permissions - for screens that several
    different roles can reach for different reasons."""

    def _check(user: dict = Depends(get_current_user)) -> dict:
        granted = set(user.get("permissions") or [])
        if not any(k in granted for k in keys):
            raise HTTPException(403, "You do not have permission to perform this action")
        return user

    return _check
