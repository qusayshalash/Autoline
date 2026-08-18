import re

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_permission
from app.services import clocks
from app.db import admin as admin_db
from app.models.schemas import (
    CreateRoleRequest,
    PermissionOut,
    RoleDetail,
    RoleSummary,
    UpdateRoleRequest,
)

router = APIRouter(prefix="/api", tags=["roles"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "role"


def _summary(row: dict) -> RoleSummary:
    return RoleSummary(
        slug=row["slug"],
        name=row["name"],
        description=row.get("description") or "",
        is_system=bool(row.get("is_system")),
        user_count=int(row.get("user_count") or 0),
        permission_count=int(row.get("permission_count") or 0),
        created_at=clocks.iso(row.get("created_at")),
        updated_at=clocks.iso(row.get("updated_at")),
    )


@router.get("/permissions", response_model=list[PermissionOut],
            dependencies=[Depends(require_permission("roles.view"))])
def list_permissions() -> list[PermissionOut]:
    return [PermissionOut(**p) for p in admin_db.list_permissions()]


@router.get("/roles", response_model=list[RoleSummary],
            dependencies=[Depends(require_permission("roles.view"))])
def list_roles() -> list[RoleSummary]:
    return [_summary(r) for r in admin_db.list_roles()]


@router.get("/roles/{slug}", response_model=RoleDetail,
            dependencies=[Depends(require_permission("roles.view"))])
def get_role(slug: str) -> RoleDetail:
    role = admin_db.get_role(slug)
    if role is None:
        raise HTTPException(404, "Role not found")
    return RoleDetail(
        slug=role["slug"],
        name=role["name"],
        description=role.get("description") or "",
        is_system=bool(role.get("is_system")),
        user_count=admin_db.count_users_with_role(slug),
        permission_count=len(role["permissions"]),
        permissions=role["permissions"],
        created_at=str(role["created_at"]) if role.get("created_at") else None,
        updated_at=str(role["updated_at"]) if role.get("updated_at") else None,
    )


def _validate_permissions(keys: list[str]) -> None:
    unknown = sorted(set(keys) - set(admin_db.ALL_PERMISSION_KEYS))
    if unknown:
        raise HTTPException(400, f"Unknown permission(s): {', '.join(unknown)}")


@router.post("/roles", response_model=RoleDetail)
def create_role(body: CreateRoleRequest, actor: dict = Depends(require_permission("roles.manage"))) -> RoleDetail:
    _validate_permissions(body.permissions)
    slug = _slugify(body.name)
    if admin_db.get_role(slug) is not None:
        raise HTTPException(409, "A role with a similar name already exists")
    admin_db.create_role(slug, body.name, body.description, body.permissions)
    admin_db.log_activity(
        actor, "role.created", "role", slug, body.name, f"{len(body.permissions)} permissions"
    )
    return get_role(slug)


@router.patch("/roles/{slug}", response_model=RoleDetail)
def update_role(
    slug: str, body: UpdateRoleRequest, actor: dict = Depends(require_permission("roles.manage"))
) -> RoleDetail:
    role = admin_db.get_role(slug)
    if role is None:
        raise HTTPException(404, "Role not found")
    if slug == admin_db.PROTECTED_ROLE and body.permissions is not None:
        raise HTTPException(409, "The Super Admin role always holds every permission")
    if role.get("is_system") and body.name is not None:
        raise HTTPException(409, "Built-in roles cannot be renamed")
    if body.permissions is not None:
        _validate_permissions(body.permissions)

    admin_db.update_role(slug, body.name, body.description, body.permissions)
    changed = [k for k, v in body.model_dump(exclude_none=True).items()]
    admin_db.log_activity(actor, "role.updated", "role", slug, role["name"], ", ".join(changed))
    return get_role(slug)


@router.delete("/roles/{slug}")
def delete_role(slug: str, actor: dict = Depends(require_permission("roles.manage"))) -> dict:
    role = admin_db.get_role(slug)
    if role is None:
        raise HTTPException(404, "Role not found")
    if role.get("is_system"):
        raise HTTPException(409, "Built-in roles cannot be deleted")
    in_use = admin_db.count_users_with_role(slug)
    if in_use:
        raise HTTPException(409, f"{in_use} user(s) still have this role")
    admin_db.delete_role(slug)
    admin_db.log_activity(actor, "role.deleted", "role", slug, role["name"])
    return {"deleted": True}
