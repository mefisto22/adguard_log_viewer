"""Saved filters — named, reusable filter trees."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from app.filters.nodes import parse_filter
from app.i18n import Message


def _row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(row["filter_json"])
    except (ValueError, TypeError):
        payload = None
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "filter": payload,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_saved_filters(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM saved_filters ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [_row(row) for row in rows]


def get_saved_filter(conn: sqlite3.Connection, filter_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM saved_filters WHERE id = ?", (filter_id,)).fetchone()
    return _row(row) if row else None


#: An empty filter matches everything, which makes a saved filter pointless and
#: — worse — indistinguishable from one whose conditions were lost on the way
#: in. Storing one used to be allowed, and the UI then showed a condition count
#: for a filter that narrowed nothing.
EMPTY_FILTER_MESSAGE = Message(
    "A saved filter needs at least one condition. An empty filter matches every "
    "query, which is the same as having no filter at all."
)


def _normalise(payload: Any) -> str:
    node = parse_filter(payload)
    if node is None:
        raise ValueError(EMPTY_FILTER_MESSAGE)
    return json.dumps(node.as_dict())


def create_saved_filter(
    conn: sqlite3.Connection, *, name: str, filter_payload: Any, description: str = ""
) -> int:
    name = name.strip()
    if not name:
        raise ValueError(Message("A saved filter needs a name"))
    existing = conn.execute("SELECT id FROM saved_filters WHERE name = ?", (name,)).fetchone()
    if existing:
        raise ValueError(Message("A saved filter named {name} already exists", name=repr(name)))

    now = int(time.time())
    cursor = conn.execute(
        "INSERT INTO saved_filters (name, description, filter_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, description.strip(), _normalise(filter_payload), now, now),
    )
    return int(cursor.lastrowid or 0)


def update_saved_filter(
    conn: sqlite3.Connection,
    filter_id: int,
    *,
    name: str | None = None,
    filter_payload: Any = None,
    description: str | None = None,
) -> bool:
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        if not name.strip():
            raise ValueError(Message("A saved filter needs a name"))
        sets.append("name = ?")
        params.append(name.strip())
    if description is not None:
        sets.append("description = ?")
        params.append(description.strip())
    if filter_payload is not None:
        sets.append("filter_json = ?")
        params.append(_normalise(filter_payload))
    if not sets:
        return False
    sets.append("updated_at = ?")
    params.append(int(time.time()))
    params.append(filter_id)
    cursor = conn.execute(
        f"UPDATE saved_filters SET {', '.join(sets)} WHERE id = ?", tuple(params)
    )
    return bool(cursor.rowcount)


def delete_saved_filter(conn: sqlite3.Connection, filter_id: int) -> bool:
    cursor = conn.execute("DELETE FROM saved_filters WHERE id = ?", (filter_id,))
    return bool(cursor.rowcount)
