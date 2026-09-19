"""Small helpers shared by the service layer."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, TypeVar

T = TypeVar("T")

#: SQLite's default limit is 999 bound parameters per statement.
MAX_PARAMS = 900


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def chunked(items: Sequence[T], size: int = MAX_PARAMS) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))


# -- key/value tables -------------------------------------------------------


def kv_get(conn: sqlite3.Connection, table: str, key: str, default: Any = None) -> Any:
    row = conn.execute(f"SELECT value FROM {table} WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (ValueError, TypeError):
        return row["value"]


def kv_set(conn: sqlite3.Connection, table: str, key: str, value: Any) -> None:
    conn.execute(
        f"INSERT INTO {table} (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def kv_all(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in conn.execute(f"SELECT key, value FROM {table}"):
        try:
            result[row["key"]] = json.loads(row["value"])
        except (ValueError, TypeError):
            result[row["key"]] = row["value"]
    return result


def kv_delete(conn: sqlite3.Connection, table: str, key: str) -> None:
    conn.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
