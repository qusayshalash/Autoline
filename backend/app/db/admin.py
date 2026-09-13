"""Roles, permissions, activity log and app settings.

Shares the catalog's connection and lock - it is one DuckDB file with a single writer.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.catalog import db_lock, get_connection
from app.services import clocks

# ---------------------------------------------------------------------------
# Permission catalogue
#
# Every entry here is enforced somewhere in the API. Adding a row without a matching
# guard would put a switch in the UI that controls nothing, so the two are kept in step
# deliberately: see `require_permission` in app/auth.py for the enforcement side.
# ---------------------------------------------------------------------------

PERMISSIONS: list[tuple[str, str, str]] = [
    # key, module, action
    ("datasets.view", "datasets", "view"),
    ("datasets.upload", "datasets", "create"),
    ("datasets.clean", "datasets", "update"),
    ("datasets.delete", "datasets", "delete"),
    ("datasets.export", "datasets", "export"),
    ("users.view", "users", "view"),
    ("users.create", "users", "create"),
    ("users.update", "users", "update"),
    ("users.delete", "users", "delete"),
    ("roles.view", "roles", "view"),
    ("roles.manage", "roles", "manage"),
    ("languages.manage", "languages", "manage"),
    ("activity.view", "activity", "view"),
    # Pruning the audit trail is deliberately not part of "manage the system". It is
    # seeded onto super_admin alone - the loop below grants every permission to that role
    # and to no other, so an existing admin role does not silently gain it on upgrade.
    ("activity.purge", "activity", "delete"),
    ("system.view", "system", "view"),
    # Split out of system.view, which used to gate the writes as well - so a role could
    # not be given sight of disk usage and backup history without also being handed the
    # retention policy that deletes files. See _split_system_view for how existing
    # installs keep what they had.
    ("system.manage", "system", "manage"),
]

ALL_PERMISSION_KEYS = [p[0] for p in PERMISSIONS]

# What a full administrator gets. Everything except pruning the audit trail: an admin who
# can erase the record of what they did leaves a log that proves nothing, so that one
# stays with the single protected role. Written as a subtraction so a permission added
# later reaches admin by default and has to be excluded on purpose.
ADMIN_PERMISSION_KEYS = [k for k in ALL_PERMISSION_KEYS if k != "activity.purge"]

# Built-in roles. The permission sets reproduce exactly what the role guards allowed
# before permissions existed, so upgrading changes nobody's access.
SYSTEM_ROLES: list[dict] = [
    {
        "slug": "super_admin",
        "name": "Super Admin",
        "description": "Full access to the system, including roles and system settings.",
        "permissions": ALL_PERMISSION_KEYS,
    },
    {
        "slug": "admin",
        "name": "Admin",
        "description": "Manages users, files and system configuration.",
        "permissions": ADMIN_PERMISSION_KEYS,
    },
    {
        "slug": "editor",
        "name": "Editor",
        "description": "Uploads, cleans and exports data. Cannot manage users or delete files.",
        "permissions": [
            "datasets.view",
            "datasets.upload",
            "datasets.clean",
            "datasets.export",
        ],
    },
    {
        "slug": "viewer",
        "name": "Viewer",
        "description": "Reads data only. Cannot upload, change or export.",
        "permissions": ["datasets.view"],
    },
]

# a role that must always exist and always keep every permission
PROTECTED_ROLE = "super_admin"


def _now() -> datetime:
    # naive UTC: see app/services/clocks.py for why an aware value cannot be stored here
    return clocks.now()


def new_id() -> str:
    return uuid.uuid4().hex


def _split_system_view(conn) -> None:
    """Gives system.manage to every role that already held system.view.

    system.manage did not exist before; system.view gated both reading system state and
    changing it. Seeding alone would not reach a built-in role that already exists - only
    super_admin picks up later permissions - so an upgrade would quietly take backups and
    retention away from the Admin role on every installation already running.

    This is a split of one permission into two, not a new capability, so the rule is that
    nobody loses anything: whoever could do it yesterday can still do it today, and the
    separation only matters for roles created from here on. It runs on every startup and
    does nothing after the first, since the grants it would add are already there.
    """
    conn.execute(
        "INSERT INTO role_permissions (role_slug, permission_key)"
        " SELECT role_slug, 'system.manage' FROM role_permissions"
        " WHERE permission_key = 'system.view'"
        " ON CONFLICT DO NOTHING"
    )


def seed() -> None:
    """Writes the permission catalogue and the built-in roles.

    Runs on every startup and is idempotent. Custom roles and any permission edits made
    to the non-super-admin built-ins are left untouched, so an administrator's changes
    survive a restart.
    """
    conn = get_connection()
    with db_lock:
        for key, module, action in PERMISSIONS:
            conn.execute(
                "INSERT INTO permissions (key, module, action) VALUES (?, ?, ?) "
                "ON CONFLICT (key) DO UPDATE SET module = excluded.module, action = excluded.action",
                [key, module, action],
            )

        for role in SYSTEM_ROLES:
            exists = conn.execute(
                "SELECT COUNT(*) FROM roles WHERE slug = ?", [role["slug"]]
            ).fetchone()[0]
            if not exists:
                conn.execute(
                    "INSERT INTO roles (slug, name, description, is_system, created_at, updated_at)"
                    " VALUES (?, ?, ?, true, ?, ?)",
                    [role["slug"], role["name"], role["description"], _now(), _now()],
                )
                for key in role["permissions"]:
                    conn.execute(
                        "INSERT INTO role_permissions (role_slug, permission_key) VALUES (?, ?)"
                        " ON CONFLICT DO NOTHING",
                        [role["slug"], key],
                    )

        _split_system_view(conn)

        # super admin always holds every permission, including ones added by a later
        # version of the app
        for key in ALL_PERMISSION_KEYS:
            conn.execute(
                "INSERT INTO role_permissions (role_slug, permission_key) VALUES (?, ?)"
                " ON CONFLICT DO NOTHING",
                [PROTECTED_ROLE, key],
            )


# ---- permissions ----

def list_permissions() -> list[dict]:
    conn = get_connection()
    with db_lock:
        rows = conn.execute(
            "SELECT key, module, action FROM permissions ORDER BY module, action"
        ).fetchall()
    return [{"key": r[0], "module": r[1], "action": r[2]} for r in rows]


def permissions_for_role(slug: str) -> list[str]:
    conn = get_connection()
    with db_lock:
        rows = conn.execute(
            "SELECT permission_key FROM role_permissions WHERE role_slug = ?", [slug]
        ).fetchall()
    return [r[0] for r in rows]


# ---- roles ----

def list_roles() -> list[dict]:
    conn = get_connection()
    with db_lock:
        rows = conn.execute(
            """
            SELECT r.slug, r.name, r.description, r.is_system, r.created_at, r.updated_at,
                   (SELECT COUNT(*) FROM users u WHERE u.role = r.slug) AS user_count,
                   (SELECT COUNT(*) FROM role_permissions rp WHERE rp.role_slug = r.slug)
                       AS permission_count
            FROM roles r
            ORDER BY r.is_system DESC, r.name
            """
        ).fetchall()
        cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


def get_role(slug: str) -> Optional[dict]:
    conn = get_connection()
    with db_lock:
        row = conn.execute("SELECT * FROM roles WHERE slug = ?", [slug]).fetchone()
        cols = [d[0] for d in conn.description]
    if row is None:
        return None
    role = dict(zip(cols, row))
    role["permissions"] = permissions_for_role(slug)
    return role


def create_role(slug: str, name: str, description: str, permissions: list[str]) -> None:
    conn = get_connection()
    with db_lock:
        conn.execute(
            "INSERT INTO roles (slug, name, description, is_system, created_at, updated_at)"
            " VALUES (?, ?, ?, false, ?, ?)",
            [slug, name, description, _now(), _now()],
        )
        for key in permissions:
            conn.execute(
                "INSERT INTO role_permissions (role_slug, permission_key) VALUES (?, ?)"
                " ON CONFLICT DO NOTHING",
                [slug, key],
            )


def update_role(
    slug: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    permissions: Optional[list[str]] = None,
) -> None:
    conn = get_connection()
    with db_lock:
        if name is not None or description is not None:
            fields: dict[str, Any] = {}
            if name is not None:
                fields["name"] = name
            if description is not None:
                fields["description"] = description
            fields["updated_at"] = _now()
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE roles SET {set_clause} WHERE slug = ?", [*fields.values(), slug]
            )
        if permissions is not None:
            conn.execute("DELETE FROM role_permissions WHERE role_slug = ?", [slug])
            for key in permissions:
                conn.execute(
                    "INSERT INTO role_permissions (role_slug, permission_key) VALUES (?, ?)",
                    [slug, key],
                )
            conn.execute("UPDATE roles SET updated_at = ? WHERE slug = ?", [_now(), slug])


def delete_role(slug: str) -> None:
    conn = get_connection()
    with db_lock:
        conn.execute("DELETE FROM role_permissions WHERE role_slug = ?", [slug])
        conn.execute("DELETE FROM roles WHERE slug = ?", [slug])


def count_active_user_managers(exclude_user_id: Optional[str] = None) -> int:
    """Active accounts that can still administer users.

    Replaces the old "last active admin" check: with custom roles, the thing worth
    protecting is not the literal admin role but the ability to manage users at all -
    losing it would lock everyone out of the panel.
    """
    conn = get_connection()
    sql = """
        SELECT COUNT(*) FROM users u
        JOIN role_permissions rp ON rp.role_slug = u.role
        WHERE rp.permission_key = 'users.update' AND u.status = 'active'
    """
    params: list = []
    if exclude_user_id:
        sql += " AND u.id != ?"
        params.append(exclude_user_id)
    with db_lock:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0


def count_users_with_role(slug: str) -> int:
    conn = get_connection()
    with db_lock:
        row = conn.execute("SELECT COUNT(*) FROM users WHERE role = ?", [slug]).fetchone()
    return row[0] if row else 0


# ---- activity log ----

def log_activity(
    actor: Optional[dict],
    action: str,
    target_type: str = "",
    target_id: str = "",
    target_label: str = "",
    detail: str = "",
    detail_code: str = "",
    **detail_params: Any,
) -> None:
    """Records one administrative event. Never raises: a failure to log must not fail
    the operation the user actually asked for.

    `detail` is the English sentence - "9 -> 8 rows" - and stays, both for the rows
    already written and for anyone reading this table with SQL. `detail_code` plus its
    parameters are the same information in a form the interface can translate; without
    one the entry simply shows the sentence, which is what every older row does.

    The two are written from the same call on purpose. Composing the sentence in one
    place and the key in another is how they drift.
    """
    try:
        envelope = (
            json.dumps({"code": detail_code, "params": detail_params}, ensure_ascii=False)
            if detail_code
            else None
        )
        conn = get_connection()
        with db_lock:
            conn.execute(
                """
                INSERT INTO activity_log
                    (id, occurred_at, actor_id, actor_username, action, target_type, target_id,
                     target_label, detail, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    new_id(),
                    _now(),
                    (actor or {}).get("id", ""),
                    (actor or {}).get("username", "system"),
                    action,
                    target_type,
                    target_id,
                    target_label,
                    detail,
                    envelope,
                ],
            )
    except Exception:  # noqa: BLE001 - logging is best-effort by design
        pass


def list_activity(
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> tuple[list[dict], int]:
    where: list[str] = []
    params: list = []
    if action:
        where.append("action = ?")
        params.append(action)
    if actor_id:
        where.append("actor_id = ?")
        params.append(actor_id)
    clause = f" WHERE {' AND '.join(where)}" if where else ""

    conn = get_connection()
    with db_lock:
        total = conn.execute(f"SELECT COUNT(*) FROM activity_log{clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM activity_log{clause} ORDER BY occurred_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows], total


def count_activity_before(cutoff: datetime) -> int:
    """How many entries a purge at this cutoff would remove. Asked before deleting, so
    the confirmation names a real number rather than a guess."""
    conn = get_connection()
    with db_lock:
        return conn.execute(
            "SELECT COUNT(*) FROM activity_log WHERE occurred_at < ?", [cutoff]
        ).fetchone()[0]


def purge_activity_before(cutoff: datetime) -> int:
    """Deletes every entry older than the cutoff and reports how many went.

    Only ever a cutoff - there is no way to delete one entry, or entries by actor, or by
    action. A trail that can be edited selectively is not evidence of anything, and the
    line most worth erasing would be the one somebody wanted gone. Age is the only filter
    that cannot be aimed.
    """
    conn = get_connection()
    with db_lock:
        removed = conn.execute(
            "SELECT COUNT(*) FROM activity_log WHERE occurred_at < ?", [cutoff]
        ).fetchone()[0]
        conn.execute("DELETE FROM activity_log WHERE occurred_at < ?", [cutoff])
    return removed


# ---- settings ----

def get_setting(key: str, default: Any = None) -> Any:
    conn = get_connection()
    with db_lock:
        row = conn.execute("SELECT value_json FROM app_settings WHERE key = ?", [key]).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return default


def set_setting(key: str, value: Any) -> None:
    conn = get_connection()
    with db_lock:
        conn.execute(
            "INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value_json = excluded.value_json,"
            " updated_at = excluded.updated_at",
            [key, json.dumps(value, ensure_ascii=False), _now()],
        )
