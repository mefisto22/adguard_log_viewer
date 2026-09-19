"""Devices (clients) and the people they belong to.

A device is identified by its IP address. Its display name is the user's alias
when set, otherwise the name AdGuard reports. Assigning a device to a person is
what makes "show me everything Peter's devices did" a single filter.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from app.db.sqlutil import chunked, placeholders
from app.i18n import Message
from app.services import dashboard_service

CLIENT_SELECT = """
SELECT c.id, c.ip, c.adguard_name, c.alias, c.person_id,
       COALESCE(NULLIF(c.alias, ''), NULLIF(c.adguard_name, ''), c.ip) AS display_name,
       c.first_seen_ns, c.last_seen_ns, c.query_count, c.blocked_count,
       p.name AS person_name, p.color AS person_color
FROM clients c
LEFT JOIN persons p ON p.id = c.person_id
"""


def _client_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "ip": row["ip"],
        "adguard_name": row["adguard_name"],
        "alias": row["alias"],
        "name": row["display_name"],
        "person_id": row["person_id"],
        "person": row["person_name"],
        "person_color": row["person_color"],
        "first_seen_ns": row["first_seen_ns"],
        "last_seen_ns": row["last_seen_ns"],
        "query_count": row["query_count"],
        "blocked_count": row["blocked_count"],
    }


# -- devices ----------------------------------------------------------------


def list_devices(
    conn: sqlite3.Connection,
    *,
    search: str = "",
    person_id: int | None = None,
    sort: str = "query_count",
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if search:
        clauses.append(
            "(c.ip LIKE ? OR c.alias LIKE ? OR c.adguard_name LIKE ? OR p.name LIKE ?)"
        )
        pattern = f"%{search}%"
        params.extend([pattern] * 4)
    if person_id is not None:
        clauses.append("c.person_id = ?")
        params.append(person_id)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = {
        "query_count": "c.query_count DESC",
        "last_seen": "c.last_seen_ns DESC",
        "first_seen": "c.first_seen_ns DESC",
        "name": "display_name COLLATE NOCASE ASC",
        "ip": "c.ip ASC",
        "blocked": "c.blocked_count DESC",
    }.get(sort, "c.query_count DESC")

    rows = conn.execute(
        f"{CLIENT_SELECT}{where} ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, max(1, min(limit, 1000)), max(0, offset)),
    ).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM clients c LEFT JOIN persons p ON p.id = c.person_id {where}",
        tuple(params),
    ).fetchone()["n"]

    return {"items": [_client_row(row) for row in rows], "total": int(total)}


def get_device(conn: sqlite3.Connection, client_id: int) -> dict[str, Any] | None:
    row = conn.execute(f"{CLIENT_SELECT}WHERE c.id = ?", (client_id,)).fetchone()
    return _client_row(row) if row else None


def update_device(
    conn: sqlite3.Connection,
    client_id: int,
    *,
    alias: str | None = None,
    person_id: int | None = None,
    clear_person: bool = False,
) -> bool:
    sets: list[str] = []
    params: list[Any] = []
    if alias is not None:
        sets.append("alias = ?")
        params.append(alias.strip())
    if clear_person:
        sets.append("person_id = NULL")
    elif person_id is not None:
        sets.append("person_id = ?")
        params.append(person_id)
    if not sets:
        return False
    params.append(client_id)
    cursor = conn.execute(f"UPDATE clients SET {', '.join(sets)} WHERE id = ?", tuple(params))
    return bool(cursor.rowcount)


def delete_device(conn: sqlite3.Connection, client_id: int) -> bool:
    """Forget a device and everything it did."""
    cursor = conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    return bool(cursor.rowcount)


def device_detail(
    conn: sqlite3.Connection,
    client_id: int,
    *,
    from_ns: int | None = None,
    to_ns: int | None = None,
    top_limit: int = 10,
) -> dict[str, Any] | None:
    device = get_device(conn, client_id)
    if device is None:
        return None

    from app.filters.nodes import Predicate

    node = Predicate(field="client_id", operator="equals", value=client_id)
    scope: dict[str, Any] = {"from_ns": from_ns, "to_ns": to_ns, "limit": top_limit}
    return {
        "device": device,
        "summary": dashboard_service.summary(
            conn, filter_node=node, from_ns=from_ns, to_ns=to_ns
        ),
        "timeline": dashboard_service.timeline(
            conn, filter_node=node, from_ns=from_ns, to_ns=to_ns, buckets=48
        ),
        "top_domains": dashboard_service.top_domains(conn, filter_node=node, **scope),
        "top_blocked_domains": dashboard_service.top_blocked_domains(
            conn, filter_node=node, **scope
        ),
        "top_categories": dashboard_service.top_categories(conn, filter_node=node, **scope),
        "top_tags": dashboard_service.top_tags(conn, filter_node=node, **scope),
        "top_query_types": dashboard_service.top_query_types(conn, filter_node=node, **scope),
    }


# -- persons ----------------------------------------------------------------


def list_persons(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT p.id, p.name, p.color, p.note, "
        "       COUNT(c.id) AS device_count, "
        "       COALESCE(SUM(c.query_count), 0) AS query_count, "
        "       COALESCE(SUM(c.blocked_count), 0) AS blocked_count, "
        "       COALESCE(MAX(c.last_seen_ns), 0) AS last_seen_ns "
        "FROM persons p LEFT JOIN clients c ON c.person_id = p.id "
        "GROUP BY p.id ORDER BY p.name COLLATE NOCASE"
    ).fetchall()
    persons = [dict(row) for row in rows]

    ids = [person["id"] for person in persons]
    devices: dict[int, list[dict[str, Any]]] = {person_id: [] for person_id in ids}
    for batch in chunked(ids):
        if not batch:
            break
        for row in conn.execute(
            f"{CLIENT_SELECT}WHERE c.person_id IN ({placeholders(len(batch))}) "
            "ORDER BY c.query_count DESC",
            tuple(batch),
        ):
            devices.setdefault(int(row["person_id"]), []).append(_client_row(row))

    for person in persons:
        person["devices"] = devices.get(person["id"], [])
    return persons


def create_person(
    conn: sqlite3.Connection, *, name: str, color: str = "", note: str = ""
) -> int:
    name = name.strip()
    if not name:
        raise ValueError(Message("A person needs a name"))
    cursor = conn.execute(
        "INSERT INTO persons (name, color, note, created_at) VALUES (?, ?, ?, ?)",
        (name, color.strip(), note.strip(), int(time.time())),
    )
    return int(cursor.lastrowid or 0)


def update_person(
    conn: sqlite3.Connection,
    person_id: int,
    *,
    name: str | None = None,
    color: str | None = None,
    note: str | None = None,
) -> bool:
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        if not name.strip():
            raise ValueError(Message("A person needs a name"))
        sets.append("name = ?")
        params.append(name.strip())
    if color is not None:
        sets.append("color = ?")
        params.append(color.strip())
    if note is not None:
        sets.append("note = ?")
        params.append(note.strip())
    if not sets:
        return False
    params.append(person_id)
    cursor = conn.execute(f"UPDATE persons SET {', '.join(sets)} WHERE id = ?", tuple(params))
    return bool(cursor.rowcount)


def delete_person(conn: sqlite3.Connection, person_id: int) -> bool:
    """Delete a person. Their devices stay, just unassigned."""
    cursor = conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    return bool(cursor.rowcount)


def assign_devices(conn: sqlite3.Connection, person_id: int | None, client_ids: list[int]) -> int:
    if not client_ids:
        return 0
    changed = 0
    for batch in chunked(client_ids):
        cursor = conn.execute(
            f"UPDATE clients SET person_id = ? WHERE id IN ({placeholders(len(batch))})",
            (person_id, *batch),
        )
        changed += cursor.rowcount or 0
    return changed


def person_detail(
    conn: sqlite3.Connection,
    person_id: int,
    *,
    from_ns: int | None = None,
    to_ns: int | None = None,
    top_limit: int = 10,
) -> dict[str, Any] | None:
    row = conn.execute("SELECT id, name, color, note FROM persons WHERE id = ?", (person_id,))
    person = row.fetchone()
    if person is None:
        return None

    from app.filters.nodes import Predicate

    node = Predicate(field="person_id", operator="equals", value=person_id)
    scope: dict[str, Any] = {"from_ns": from_ns, "to_ns": to_ns, "limit": top_limit}
    devices = [
        _client_row(device)
        for device in conn.execute(
            f"{CLIENT_SELECT}WHERE c.person_id = ? ORDER BY c.query_count DESC", (person_id,)
        )
    ]
    return {
        "person": {**dict(person), "devices": devices},
        "summary": dashboard_service.summary(
            conn, filter_node=node, from_ns=from_ns, to_ns=to_ns
        ),
        "timeline": dashboard_service.timeline(
            conn, filter_node=node, from_ns=from_ns, to_ns=to_ns, buckets=48
        ),
        "top_domains": dashboard_service.top_domains(conn, filter_node=node, **scope),
        "top_blocked_domains": dashboard_service.top_blocked_domains(
            conn, filter_node=node, **scope
        ),
        "top_categories": dashboard_service.top_categories(conn, filter_node=node, **scope),
        "top_tags": dashboard_service.top_tags(conn, filter_node=node, **scope),
        "top_clients": dashboard_service.top_clients(conn, filter_node=node, **scope),
    }
