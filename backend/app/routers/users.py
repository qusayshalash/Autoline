import duckdb
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_permission
from app.db import admin as admin_db
from app.db import catalog
from app.models.schemas import CreateUserRequest, UpdateUserRequest, UserOut
from app.services import security

router = APIRouter(prefix="/api/users", tags=["users"])

VALID_STATUSES = {"active", "inactive", "suspended", "pending"}


def _user_out(row: dict) -> UserOut:
    return UserOut(
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
    )


def _require_role_exists(slug: str) -> None:
    if admin_db.get_role(slug) is None:
        raise HTTPException(400, f"Unknown role: {slug}")


@router.get("", response_model=list[UserOut], dependencies=[Depends(require_permission("users.view"))])
def list_users() -> list[UserOut]:
    return [_user_out(u) for u in catalog.list_users()]


@router.post("", response_model=UserOut)
def create_user(body: CreateUserRequest, actor: dict = Depends(require_permission("users.create"))) -> UserOut:
    _require_role_exists(body.role)
    if body.status not in VALID_STATUSES:
        raise HTTPException(400, f"Unknown status: {body.status}")
    if catalog.get_user_by_username(body.username) is not None:
        raise HTTPException(409, "Username already exists")

    user_id = catalog.new_id()
    try:
        catalog.create_user(
            user_id,
            body.username,
            security.hash_password(body.password),
            body.role,
            full_name=body.full_name or "",
            email=body.email or "",
            status=body.status,
        )
    except duckdb.Error as exc:
        # a concurrent request created the same username between our check and the insert
        raise HTTPException(409, "Username already exists") from exc

    admin_db.log_activity(
        actor, "user.created", "user", user_id, body.username, f"role={body.role}"
    )
    return _user_out(catalog.get_user_by_id(user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str, body: UpdateUserRequest, actor: dict = Depends(require_permission("users.update"))
) -> UserOut:
    row = catalog.get_user_by_id(user_id)
    if row is None:
        raise HTTPException(404, "User not found")

    current_status = row.get("status") or ("active" if row.get("is_active") else "inactive")
    next_status = body.status if body.status is not None else current_status
    next_role = body.role if body.role is not None else row["role"]

    if body.role is not None:
        _require_role_exists(body.role)
    if body.status is not None and body.status not in VALID_STATUSES:
        raise HTTPException(400, f"Unknown status: {body.status}")

    # Guard the ability to administer users at all, rather than a specific role name.
    would_lose_management = next_status != "active" or "users.update" not in admin_db.permissions_for_role(next_role)
    if would_lose_management and admin_db.count_active_user_managers(exclude_user_id=user_id) == 0:
        raise HTTPException(409, "Cannot remove the last account that can manage users")

    fields: dict = {}
    if body.role is not None:
        fields["role"] = body.role
    if body.status is not None:
        fields["status"] = body.status
    if body.full_name is not None:
        fields["full_name"] = body.full_name
    if body.email is not None:
        fields["email"] = body.email
    if body.password:
        fields["password_hash"] = security.hash_password(body.password)

    catalog.update_user(user_id, **fields)

    changed = [k for k in fields if k not in ("updated_at", "is_active")]
    action = "user.password_reset" if changed == ["password_hash"] else "user.updated"
    admin_db.log_activity(
        actor, action, "user", user_id, row["username"], ", ".join(changed)
    )
    return _user_out(catalog.get_user_by_id(user_id))


@router.delete("/{user_id}")
def delete_user(user_id: str, actor: dict = Depends(require_permission("users.delete"))) -> dict:
    row = catalog.get_user_by_id(user_id)
    if row is None:
        raise HTTPException(404, "User not found")
    if admin_db.count_active_user_managers(exclude_user_id=user_id) == 0:
        raise HTTPException(409, "Cannot delete the last account that can manage users")
    catalog.delete_user(user_id)
    admin_db.log_activity(actor, "user.deleted", "user", user_id, row["username"])
    return {"deleted": True}
