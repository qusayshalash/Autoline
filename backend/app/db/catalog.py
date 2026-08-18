"""Central catalog: one small DuckDB file tracking dataset metadata, background jobs,
and cleaning-operation history. Kept separate from per-dataset files so listing datasets
never requires opening every dataset's (potentially huge) database.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import duckdb

from app.config import settings
from app.services import clocks

_lock = threading.Lock()
_conn: Optional[duckdb.DuckDBPyConnection] = None


def _connection() -> duckdb.DuckDBPyConnection:
    global _conn
    with _lock:
        if _conn is None:
            settings.ensure_dirs()
            _conn = duckdb.connect(str(settings.catalog_path))
            _init_schema(_conn)
        return _conn


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            id VARCHAR PRIMARY KEY,
            original_filename VARCHAR,
            status VARCHAR,               -- uploading|normalizing|importing|ready|cleaning|error
            error_message VARCHAR,
            encoding VARCHAR,
            delimiter VARCHAR,
            has_header BOOLEAN,
            columns_json VARCHAR,
            row_count_raw BIGINT,
            row_count_cleaned BIGINT,
            raw_file_bytes BIGINT,
            cleaned_file_bytes BIGINT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id VARCHAR PRIMARY KEY,
            dataset_id VARCHAR,
            kind VARCHAR,                 -- import|clean|export
            status VARCHAR,               -- pending|running|done|error
            progress VARCHAR,
            result_json VARCHAR,
            error_message VARCHAR,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cleaning_operations (
            id VARCHAR PRIMARY KEY,
            dataset_id VARCHAR,
            config_json VARCHAR,
            rows_before BIGINT,
            rows_after BIGINT,
            duplicates_removed BIGINT,
            filtered_out BIGINT,
            columns_dropped_json VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR PRIMARY KEY,
            username VARCHAR UNIQUE,
            password_hash VARCHAR,
            role VARCHAR,              -- slug into roles.slug
            is_active BOOLEAN,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    # Roles are data rather than code so that custom roles can be created at runtime.
    # `slug` is the key: users.role stores it, and it is what the session token carries.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            slug VARCHAR PRIMARY KEY,
            name VARCHAR,
            description VARCHAR,
            is_system BOOLEAN,         -- built-in roles cannot be renamed or deleted
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    # The permission catalogue is fixed by what the application can actually do, so it is
    # seeded from code on every start - a permission with no enforcement behind it would
    # be a lie.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS permissions (
            key VARCHAR PRIMARY KEY,   -- e.g. datasets.delete
            module VARCHAR,            -- datasets|users|roles|languages|activity|system
            action VARCHAR             -- view|create|update|delete|export|manage
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_slug VARCHAR,
            permission_key VARCHAR,
            PRIMARY KEY (role_slug, permission_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id VARCHAR PRIMARY KEY,
            occurred_at TIMESTAMP,     -- "at" is reserved in DuckDB
            actor_id VARCHAR,
            actor_username VARCHAR,
            action VARCHAR,            -- user.created, dataset.deleted, role.updated, ...
            target_type VARCHAR,       -- user|dataset|role|language|system
            target_id VARCHAR,
            target_label VARCHAR,
            detail VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key VARCHAR PRIMARY KEY,
            value_json VARCHAR,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            key VARCHAR PRIMARY KEY,      -- 'user:<username>' or 'ip:<address>'
            failures INTEGER,
            first_failure_at TIMESTAMP,
            last_failure_at TIMESTAMP,
            locked_until TIMESTAMP
        )
        """
    )
    _migrate_users(conn)
    _migrate_datasets(conn)


def _migrate_datasets(conn: duckdb.DuckDBPyConnection) -> None:
    """Adds the import-quality report to an existing datasets table, in place."""
    existing = {r[0] for r in conn.execute("DESCRIBE datasets").fetchall()}
    if "quality_json" not in existing:
        conn.execute("ALTER TABLE datasets ADD COLUMN quality_json VARCHAR")


def _migrate_users(conn: duckdb.DuckDBPyConnection) -> None:
    """Adds the admin-panel columns to an existing users table.

    The app ships as a single file that people already have data in, so schema changes
    are applied in place rather than by recreating the table. Each column is added only
    when missing, and `status` is backfilled from the older `is_active` flag so existing
    accounts keep working exactly as before.
    """
    existing = {r[0] for r in conn.execute("DESCRIBE users").fetchall()}
    additions = {
        "full_name": "VARCHAR",
        "email": "VARCHAR",
        "status": "VARCHAR",       # active|inactive|suspended|pending
        "last_login_at": "TIMESTAMP",
    }
    for column, sql_type in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} {sql_type}")

    # backfill status for rows that predate the column
    conn.execute(
        "UPDATE users SET status = CASE WHEN is_active THEN 'active' ELSE 'inactive' END "
        "WHERE status IS NULL"
    )


def _now() -> datetime:
    # naive UTC: see app/services/clocks.py for why an aware value cannot be stored here
    return clocks.now()


def cursor() -> duckdb.DuckDBPyConnection:
    """An independent cursor on the catalog, for callers that run their own queries.

    Every function in this module shares one connection under `_lock`, which is fine
    because each of them finishes in microseconds. A long-running caller must not use
    that connection directly: DuckDB exposes the column names of the most recent query
    on the connection object, so a slow query running alongside a catalog read leaves the
    reader zipping its rows against somebody else's column list. A cursor is a separate
    handle onto the same database and has its own.
    """
    return _connection().cursor()


def get_connection() -> duckdb.DuckDBPyConnection:
    """Shared catalog connection, for sibling db modules (see db/admin.py)."""
    return _connection()


# the catalog is a single DuckDB file with one writer, so every module that touches it
# serialises on this lock
db_lock = _lock


def new_id() -> str:
    return uuid.uuid4().hex


# ---- datasets ----

def create_dataset(dataset_id: str, original_filename: str) -> None:
    conn = _connection()
    with _lock:
        conn.execute(
            """
            INSERT INTO datasets (id, original_filename, status, created_at, updated_at)
            VALUES (?, ?, 'uploading', ?, ?)
            """,
            [dataset_id, original_filename, _now(), _now()],
        )


def update_dataset(dataset_id: str, **fields: Any) -> None:
    if not fields:
        return
    for json_field in ("columns_json", "quality_json"):
        if json_field in fields and not isinstance(fields[json_field], (str, type(None))):
            fields[json_field] = json.dumps(fields[json_field], ensure_ascii=False)
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn = _connection()
    with _lock:
        conn.execute(
            f"UPDATE datasets SET {set_clause} WHERE id = ?",
            [*fields.values(), dataset_id],
        )


def get_dataset(dataset_id: str) -> Optional[dict]:
    conn = _connection()
    with _lock:
        row = conn.execute(
            "SELECT * FROM datasets WHERE id = ?", [dataset_id]
        ).fetchone()
        cols = [d[0] for d in conn.description]
    if row is None:
        return None
    return dict(zip(cols, row))


def list_datasets() -> list[dict]:
    conn = _connection()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM datasets ORDER BY created_at DESC"
        ).fetchall()
        cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


def delete_dataset(dataset_id: str) -> None:
    conn = _connection()
    with _lock:
        conn.execute("DELETE FROM datasets WHERE id = ?", [dataset_id])
        conn.execute("DELETE FROM jobs WHERE dataset_id = ?", [dataset_id])
        conn.execute("DELETE FROM cleaning_operations WHERE dataset_id = ?", [dataset_id])


# ---- jobs ----

def create_job(dataset_id: str, kind: str) -> str:
    job_id = new_id()
    conn = _connection()
    with _lock:
        conn.execute(
            """
            INSERT INTO jobs (id, dataset_id, kind, status, progress, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', '', ?, ?)
            """,
            [job_id, dataset_id, kind, _now(), _now()],
        )
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    if "result_json" in fields and not isinstance(fields["result_json"], str):
        fields["result_json"] = json.dumps(fields["result_json"], ensure_ascii=False)
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn = _connection()
    with _lock:
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", [*fields.values(), job_id])


def get_job(job_id: str) -> Optional[dict]:
    conn = _connection()
    with _lock:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", [job_id]).fetchone()
        cols = [d[0] for d in conn.description]
    if row is None:
        return None
    return dict(zip(cols, row))


# ---- cleaning operations ----

def record_cleaning_operation(
    dataset_id: str,
    config: dict,
    rows_before: int,
    rows_after: int,
    duplicates_removed: int,
    filtered_out: int,
    columns_dropped: list[str],
) -> None:
    conn = _connection()
    with _lock:
        conn.execute(
            """
            INSERT INTO cleaning_operations
                (id, dataset_id, config_json, rows_before, rows_after,
                 duplicates_removed, filtered_out, columns_dropped_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                new_id(),
                dataset_id,
                json.dumps(config, ensure_ascii=False),
                rows_before,
                rows_after,
                duplicates_removed,
                filtered_out,
                json.dumps(columns_dropped, ensure_ascii=False),
                _now(),
            ],
        )


def list_cleaning_operations(dataset_id: str) -> list[dict]:
    conn = _connection()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM cleaning_operations WHERE dataset_id = ? ORDER BY created_at DESC",
            [dataset_id],
        ).fetchall()
        cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


# ---- users ----

def create_user(
    user_id: str,
    username: str,
    password_hash: str,
    role: str,
    full_name: str = "",
    email: str = "",
    status: str = "active",
) -> None:
    conn = _connection()
    with _lock:
        conn.execute(
            """
            INSERT INTO users
                (id, username, password_hash, role, is_active, full_name, email, status,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                user_id,
                username,
                password_hash,
                role,
                status == "active",
                full_name,
                email,
                status,
                _now(),
                _now(),
            ],
        )


def get_user_by_username(username: str) -> Optional[dict]:
    conn = _connection()
    with _lock:
        row = conn.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
        cols = [d[0] for d in conn.description]
    if row is None:
        return None
    return dict(zip(cols, row))


def get_user_by_id(user_id: str) -> Optional[dict]:
    conn = _connection()
    with _lock:
        row = conn.execute("SELECT * FROM users WHERE id = ?", [user_id]).fetchone()
        cols = [d[0] for d in conn.description]
    if row is None:
        return None
    return dict(zip(cols, row))


def list_users() -> list[dict]:
    conn = _connection()
    with _lock:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
        cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


def update_user(user_id: str, **fields: Any) -> None:
    if not fields:
        return
    # `is_active` is what the login path checks, so it is kept derived from `status`
    # rather than being a second source of truth that can drift.
    if "status" in fields:
        fields["is_active"] = fields["status"] == "active"
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn = _connection()
    with _lock:
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", [*fields.values(), user_id])


def record_login(user_id: str) -> None:
    conn = _connection()
    with _lock:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", [_now(), user_id])


def delete_user(user_id: str) -> None:
    conn = _connection()
    with _lock:
        conn.execute("DELETE FROM users WHERE id = ?", [user_id])


def count_active_admins(exclude_user_id: Optional[str] = None) -> int:
    conn = _connection()
    with _lock:
        if exclude_user_id:
            row = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = true AND id != ?",
                [exclude_user_id],
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = true"
            ).fetchone()
    return row[0] if row else 0


def count_users() -> int:
    conn = _connection()
    with _lock:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return row[0] if row else 0
