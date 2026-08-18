from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth import COOKIE_NAME, get_current_user
from app.db import admin as admin_db
from app.db import catalog
from app.models.schemas import LoginRequest, MeOut
from app.services import login_guard, security

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _me_out(row: dict, permissions: list[str]) -> MeOut:
    return MeOut(
        id=row["id"],
        username=row["username"],
        full_name=row.get("full_name") or "",
        email=row.get("email") or "",
        role=row["role"],
        status=row.get("status") or ("active" if row.get("is_active") else "inactive"),
        is_active=bool(row.get("is_active")),
        last_login_at=str(row["last_login_at"]) if row.get("last_login_at") else None,
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
        permissions=permissions,
    )


@router.post("/login", response_model=MeOut)
def login(body: LoginRequest, request: Request, response: Response) -> MeOut:
    """Signs in, or refuses in a way that gives nothing away.

    Every refusal reads the same from outside: the same status, the same message, and the
    same amount of time spent, whether the account exists, is disabled, or the password
    was simply wrong. The only response that differs is the one for too many attempts,
    and that is driven by the username as typed - so it arrives identically for a real
    account and an invented one.
    """
    address = login_guard.client_address(request)

    verdict = login_guard.check(body.username, address)
    if not verdict.allowed:
        admin_db.log_activity(
            {"id": "", "username": body.username},
            "auth.blocked",
            "user",
            "",
            body.username,
            f"from {address}, retry in {verdict.retry_after_s}s",
        )
        raise HTTPException(
            429,
            "Too many attempts. Try again later.",
            headers={"Retry-After": str(verdict.retry_after_s)},
        )

    user = catalog.get_user_by_username(body.username)
    status = (user or {}).get("status") or ("active" if (user or {}).get("is_active") else "inactive")

    if user is None:
        # spend the same effort as a real verification, so the timing says nothing about
        # whether this username exists
        security.dummy_verify(body.password)
        ok = False
    else:
        ok = status == "active" and security.verify_password(body.password, user["password_hash"])

    if not ok:
        after = login_guard.record_failure(body.username, address)
        admin_db.log_activity(
            {"id": (user or {}).get("id", ""), "username": body.username},
            "auth.login_failed",
            "user",
            (user or {}).get("id", ""),
            body.username,
            f"from {address}, attempt {after.failures}"
            + ("" if after.allowed else f", locked for {after.retry_after_s}s"),
        )
        raise HTTPException(401, "Invalid username or password")

    login_guard.record_success(body.username)

    token = security.create_access_token(user["id"], user["username"], user["role"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # set True when served over HTTPS
        max_age=int(security.ACCESS_TOKEN_TTL.total_seconds()),
        path="/",
    )
    catalog.record_login(user["id"])
    admin_db.log_activity(user, "auth.login", "user", user["id"], user["username"])
    permissions = admin_db.permissions_for_role(user["role"])
    return _me_out(catalog.get_user_by_id(user["id"]) or user, permissions)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"logged_out": True}


@router.get("/me", response_model=MeOut)
def me(user: dict = Depends(get_current_user)) -> MeOut:
    return _me_out(user, user.get("permissions") or [])
