"""Domain listing and the per-domain detail view."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.filters.nodes import Predicate
from app.services import dashboard_service


def _domain_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "registrable_domain": row["registrable"],
        "first_seen_ns": row["first_seen_ns"],
        "last_seen_ns": row["last_seen_ns"],
        "query_count": row["query_count"],
        "blocked_count": row["blocked_count"],
    }


def _tags_for(conn: sqlite3.Connection, domain_id: int) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        "SELECT t.id, t.name, t.kind, t.color, dt.source FROM domain_tags dt "
        "JOIN tags t ON t.id = dt.tag_id WHERE dt.domain_id = ? ORDER BY t.kind, t.name",
        (domain_id,),
    ).fetchall()
    tags: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []
    for row in rows:
        entry = {
            "id": row["id"],
            "name": row["name"],
            "color": row["color"],
            "source": row["source"],
        }
        (categories if row["kind"] == "category" else tags).append(entry)
    return {"tags": tags, "categories": categories}


def list_domains(
    conn: sqlite3.Connection,
    *,
    search: str = "",
    sort: str = "query_count",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if search:
        clauses.append("(name LIKE ? OR registrable LIKE ?)")
        params.extend([f"%{search}%"] * 2)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = {
        "query_count": "query_count DESC",
        "blocked": "blocked_count DESC",
        "last_seen": "last_seen_ns DESC",
        "first_seen": "first_seen_ns DESC",
        "name": "name COLLATE NOCASE ASC",
    }.get(sort, "query_count DESC")

    rows = conn.execute(
        f"SELECT * FROM domains {where} ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, max(1, min(limit, 500)), max(0, offset)),
    ).fetchall()
    total = conn.execute(f"SELECT COUNT(*) AS n FROM domains {where}", tuple(params)).fetchone()

    items = [_domain_row(row) for row in rows]
    for item in items:
        item.update(_tags_for(conn, item["id"]))
    return {"items": items, "total": int(total["n"])}


def domain_detail(
    conn: sqlite3.Connection,
    *,
    domain_id: int | None = None,
    name: str | None = None,
    from_ns: int | None = None,
    to_ns: int | None = None,
    top_limit: int = 10,
) -> dict[str, Any] | None:
    if domain_id is not None:
        row = conn.execute("SELECT * FROM domains WHERE id = ?", (domain_id,)).fetchone()
    elif name:
        row = conn.execute("SELECT * FROM domains WHERE name = ?", (name.lower(),)).fetchone()
    else:
        return None
    if row is None:
        return None

    domain = _domain_row(row)
    domain.update(_tags_for(conn, domain["id"]))

    node = Predicate(field="domain", operator="equals", value=domain["name"])
    scope: dict[str, Any] = {"from_ns": from_ns, "to_ns": to_ns, "limit": top_limit}

    related = conn.execute(
        "SELECT id, name, query_count, blocked_count FROM domains "
        "WHERE registrable = ? AND id <> ? ORDER BY query_count DESC LIMIT ?",
        (domain["registrable_domain"], domain["id"], top_limit),
    ).fetchall()

    return {
        "domain": domain,
        "summary": dashboard_service.summary(
            conn, filter_node=node, from_ns=from_ns, to_ns=to_ns
        ),
        "timeline": dashboard_service.timeline(
            conn, filter_node=node, from_ns=from_ns, to_ns=to_ns, buckets=48
        ),
        "top_clients": dashboard_service.top_clients(conn, filter_node=node, **scope),
        "top_persons": dashboard_service.top_persons(conn, filter_node=node, **scope),
        "top_query_types": dashboard_service.top_query_types(conn, filter_node=node, **scope),
        "top_upstreams": dashboard_service.top_upstreams(conn, filter_node=node, **scope),
        "related_domains": [dict(item) for item in related],
    }
