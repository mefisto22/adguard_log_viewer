"""Reading queries out of the database.

Filtering, sorting, paging and counting all happen in SQL. The browser never
receives more than one page, and never filters client-side.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

from app.common.timeutil import iso_from_ns
from app.db.sqlutil import chunked, placeholders
from app.filters.nodes import FilterNode
from app.filters.sql_builder import compile_filter
from app.ingest.records import result_kind

_LOGGER = logging.getLogger(__name__)

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 100

#: Counting every matching row on a multi-million table is pointless for a UI
#: that shows "1-100 of ...". Stop counting here and report the total as capped.
COUNT_CAP = 50_000

SELECT_COLUMNS = """
SELECT q.id, q.ts_ns, q.qtype, q.qclass, q.status, q.reason, q.blocked,
       q.rule_text, q.filter_list_id, q.elapsed_us, q.upstream, q.cached,
       q.answer, q.answers_json, q.client_proto,
       d.id   AS domain_id, d.name AS domain, d.registrable,
       c.id   AS client_id, c.ip   AS client_ip,
       c.adguard_name, c.alias,
       p.id   AS person_id, p.name AS person
"""

LOOKUP_JOINS = """
JOIN domains d ON d.id = q.domain_id
JOIN clients c ON c.id = q.client_id
LEFT JOIN persons p ON p.id = c.person_id
"""

BASE_SELECT = f"{SELECT_COLUMNS}FROM queries q{LOOKUP_JOINS}"

#: Sorts that only touch the ``queries`` table. For those the page is selected
#: before the lookup joins happen, so the sort works on narrow rows instead of
#: fully joined ones — on a wide filter that is the difference between sorting
#: hundreds of thousands of joined rows and sorting the same count of bare ones.
QUERY_ONLY_SORTS: frozenset[str] = frozenset(
    {"time", "query_type", "response_status", "blocked", "response_time", "upstream"}
)

SORT_COLUMNS: dict[str, str] = {
    "time": "q.ts_ns",
    "domain": "d.name",
    "client": "c.ip",
    "client_name": "COALESCE(NULLIF(c.alias, ''), c.adguard_name)",
    "person": "p.name",
    "query_type": "q.qtype",
    "response_status": "q.status",
    "blocked": "q.blocked",
    "response_time": "q.elapsed_us",
    "upstream": "q.upstream",
}


@dataclass(slots=True)
class QueryPage:
    items: list[dict[str, Any]]
    limit: int
    offset: int
    total: int | None = None
    total_capped: bool = False
    has_more: bool = False
    newest_id: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "limit": self.limit,
            "offset": self.offset,
            "total": self.total,
            "total_capped": self.total_capped,
            "has_more": self.has_more,
            "newest_id": self.newest_id,
        }


def _order_clause(sort: str, direction: str) -> str:
    column = SORT_COLUMNS.get(sort, SORT_COLUMNS["time"])
    order = "ASC" if direction.lower() == "asc" else "DESC"
    # q.id is a stable tie-breaker, which also keeps paging deterministic.
    if column == "q.ts_ns":
        return f"ORDER BY q.ts_ns {order}, q.id {order}"
    return f"ORDER BY {column} {order}, q.ts_ns DESC, q.id DESC"


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    raw = row["answers_json"]
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                answers = parsed
        except ValueError:  # pragma: no cover - defensive
            answers = []

    client_name = row["alias"] or row["adguard_name"] or ""
    return {
        "id": row["id"],
        "ts_ns": row["ts_ns"],
        "time": iso_from_ns(row["ts_ns"]),
        "domain": row["domain"],
        "domain_id": row["domain_id"],
        "registrable_domain": row["registrable"],
        "client_ip": row["client_ip"],
        "client_id": row["client_id"],
        "client_name": client_name,
        "adguard_name": row["adguard_name"],
        "alias": row["alias"],
        "person": row["person"],
        "person_id": row["person_id"],
        "query_type": row["qtype"],
        "query_class": row["qclass"],
        "response_status": row["status"],
        "reason": row["reason"],
        "result": result_kind(row["reason"]),
        "blocked": bool(row["blocked"]),
        "rule": row["rule_text"],
        "filter_list_id": row["filter_list_id"],
        "response_time_ms": round(row["elapsed_us"] / 1000.0, 3) if row["elapsed_us"] else 0.0,
        "upstream": row["upstream"],
        "cached": bool(row["cached"]),
        "answer": row["answer"],
        "answers": answers,
        "client_proto": row["client_proto"],
        "tags": [],
        "categories": [],
    }


def attach_tags(conn: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    """Fill in the tags and categories for a page of results in one query."""
    if not items:
        return
    domain_ids = sorted({item["domain_id"] for item in items})
    by_domain: dict[int, list[sqlite3.Row]] = {}
    for batch in chunked(domain_ids):
        rows = conn.execute(
            "SELECT dt.domain_id, t.name, t.kind, t.color FROM domain_tags dt "
            f"JOIN tags t ON t.id = dt.tag_id WHERE dt.domain_id IN ({placeholders(len(batch))}) "
            "ORDER BY t.kind, t.name",
            tuple(batch),
        ).fetchall()
        for row in rows:
            by_domain.setdefault(int(row["domain_id"]), []).append(row)

    for item in items:
        tags: list[dict[str, str]] = []
        categories: list[dict[str, str]] = []
        for row in by_domain.get(item["domain_id"], []):
            entry = {"name": row["name"], "color": row["color"] or ""}
            (categories if row["kind"] == "category" else tags).append(entry)
        item["tags"] = tags
        item["categories"] = categories


def list_queries(
    conn: sqlite3.Connection,
    *,
    filter_node: FilterNode | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    sort: str = "time",
    direction: str = "desc",
    include_total: bool = True,
    before_id: int | None = None,
    after_id: int | None = None,
    with_tags: bool = True,
) -> QueryPage:
    """Return one page of query records."""
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))

    compiled = compile_filter(filter_node)
    params = list(compiled.params)
    clauses = [] if compiled.is_empty else [compiled.sql]

    if before_id is not None:
        clauses.append("q.id < ?")
        params.append(int(before_id))
    if after_id is not None:
        clauses.append("q.id > ?")
        params.append(int(after_id))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = _order_clause(sort, direction)

    if sort in QUERY_ONLY_SORTS:
        # Pick the page out of `queries` alone, then join the lookup tables for
        # the handful of rows that survive.
        inner = f"SELECT q.* FROM queries q\n{where}\n{order}\nLIMIT ? OFFSET ?"
        sql = f"{SELECT_COLUMNS}FROM ({inner}) q{LOOKUP_JOINS}{order}"
    else:
        sql = f"{BASE_SELECT}{where}\n{order}\nLIMIT ? OFFSET ?"
    rows = conn.execute(sql, (*params, limit + 1, offset)).fetchall()

    has_more = len(rows) > limit
    items = [_row_to_item(row) for row in rows[:limit]]
    if with_tags:
        attach_tags(conn, items)

    total: int | None = None
    capped = False
    if include_total:
        # Compiled filters only ever reference `q`, so counting needs no joins.
        count_sql = f"SELECT COUNT(*) AS n FROM (SELECT 1 FROM queries q {where} LIMIT ?)"
        row = conn.execute(count_sql, (*params, COUNT_CAP + 1)).fetchone()
        total = int(row["n"])
        if total > COUNT_CAP:
            total = COUNT_CAP
            capped = True

    newest = conn.execute("SELECT MAX(id) AS last FROM queries").fetchone()
    return QueryPage(
        items=items,
        limit=limit,
        offset=offset,
        total=total,
        total_capped=capped,
        has_more=has_more,
        newest_id=int(newest["last"] or 0),
    )


def get_query(conn: sqlite3.Connection, query_id: int) -> dict[str, Any] | None:
    row = conn.execute(f"{BASE_SELECT}WHERE q.id = ?", (query_id,)).fetchone()
    if row is None:
        return None
    item = _row_to_item(row)
    attach_tags(conn, [item])
    return item


def count_queries(conn: sqlite3.Connection, filter_node: FilterNode | None = None) -> int:
    """Exact count of matching rows. Unlike the paged listing, this is not capped."""
    compiled = compile_filter(filter_node)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM queries q {compiled.where()}", tuple(compiled.params)
    ).fetchone()
    return int(row["n"])
