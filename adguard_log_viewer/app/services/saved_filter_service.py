"""Saved filters — named, reusable filter trees."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from app.filters.nodes import parse_filter


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


def _normalise(payload: Any) -> str:
    node = parse_filter(payload)
    return json.dumps(node.as_dict() if node else {})


def create_saved_filter(
    conn: sqlite3.Connection, *, name: str, filter_payload: Any, description: str = ""
) -> int:
    name = name.strip()
    if not name:
        raise ValueError("A saved filter needs a name")
    existing = conn.execute("SELECT id FROM saved_filters WHERE name = ?", (name,)).fetchone()
    if existing:
        raise ValueError(f"A saved filter named {name!r} already exists")

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
            raise ValueError("A saved filter needs a name")
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
