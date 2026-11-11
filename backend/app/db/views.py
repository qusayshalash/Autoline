"""Saved views: a search with its filters and sort, kept under a name.

They live in the catalog - small rows, one writer - and share its connection and lock.
"""

import json
from typing import Any, Optional

from app.db.catalog import db_lock, get_connection, new_id
from app.services import clocks

def _rows(sql: str, params: list[Any]) -> list[dict]:
    conn = get_connection()
    with db_lock:
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


# ---- saved views ----


def _decode(row: dict) -> dict:
    row["state"] = json.loads(row.pop("state_json") or "{}")
    return row


def list_views(dataset_id: str, user_id: str) -> list[dict]:
    """The person's own views and everything shared, own first, each group by name."""
    return [
        _decode(r)
        for r in _rows(
            """
            SELECT * FROM saved_views
            WHERE dataset_id = ? AND (owner_id = ? OR shared)
            ORDER BY (owner_id = ?) DESC, lower(name), created_at
            """,
            [dataset_id, user_id, user_id],
        )
    ]


def get_view(view_id: str) -> Optional[dict]:
    found = _rows("SELECT * FROM saved_views WHERE id = ?", [view_id])
    return _decode(found[0]) if found else None


def count_own_views(dataset_id: str, user_id: str) -> int:
    return _rows(
        "SELECT COUNT(*) AS n FROM saved_views WHERE dataset_id = ? AND owner_id = ?",
        [dataset_id, user_id],
    )[0]["n"]


def create_view(
    dataset_id: str, owner: dict, name: str, state: dict, shared: bool
) -> str:
    view_id = new_id()
    now = clocks.now()
    conn = get_connection()
    with db_lock:
        conn.execute(
            """
            INSERT INTO saved_views
                (id, dataset_id, owner_id, owner_username, name, state_json, shared,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                view_id,
                dataset_id,
                owner["id"],
                owner.get("username") or "",
                name,
                json.dumps(state, ensure_ascii=False),
                shared,
                now,
                now,
            ],
        )
    return view_id


def update_view(view_id: str, **fields: Any) -> None:
    if "state" in fields:
        fields["state_json"] = json.dumps(fields.pop("state"), ensure_ascii=False)
    if not fields:
        return
    fields["updated_at"] = clocks.now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn = get_connection()
    with db_lock:
        conn.execute(
            f"UPDATE saved_views SET {set_clause} WHERE id = ?", [*fields.values(), view_id]
        )


def delete_view(view_id: str) -> None:
    conn = get_connection()
    with db_lock:
        conn.execute("DELETE FROM saved_views WHERE id = ?", [view_id])
