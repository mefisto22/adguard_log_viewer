"""Dashboard aggregations.

Every figure is computed in SQL over indexed columns and bounded by the selected
time range. The unfiltered activity timeline is served from the ``stats_minute``
rollup that ingest maintains, so it stays O(buckets) no matter how many queries
are stored.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

from app.common.timeutil import NS_PER_SECOND, now_ns
from app.filters.nodes import FilterNode
from app.filters.sql_builder import compile_filter

JOINS = (
    "FROM queries q "
    "JOIN domains d ON d.id = q.domain_id "
    "JOIN clients c ON c.id = q.client_id "
    "LEFT JOIN persons p ON p.id = c.person_id "
)

DEFAULT_TOP_LIMIT = 10
MAX_TOP_LIMIT = 100

#: Bucket widths the timeline snaps to, in seconds.
BUCKET_STEPS: tuple[int, ...] = (
    10, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 604800,
)


def _range_clause(from_ns: int | None, to_ns: int | None) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if from_ns is not None:
        clauses.append("q.ts_ns >= ?")
        params.append(from_ns)
    if to_ns is not None:
        clauses.append("q.ts_ns < ?")
        params.append(to_ns)
    return " AND ".join(clauses), params


def _where(
    filter_node: FilterNode | None, from_ns: int | None, to_ns: int | None
) -> tuple[str, list[Any]]:
    compiled = compile_filter(filter_node)
    clauses: list[str] = []
    params: list[Any] = []
    if not compiled.is_empty:
        clauses.append(compiled.sql)
        params.extend(compiled.params)
    range_sql, range_params = _range_clause(from_ns, to_ns)
    if range_sql:
        clauses.append(range_sql)
        params.extend(range_params)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def summary(
    conn: sqlite3.Connection,
    *,
    filter_node: FilterNode | None = None,
    from_ns: int | None = None,
    to_ns: int | None = None,
) -> dict[str, Any]:
    where, params = _where(filter_node, from_ns, to_ns)
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "       COALESCE(SUM(q.blocked), 0) AS blocked, "
        "       COUNT(DISTINCT q.domain_id) AS unique_domains, "
        "       COUNT(DISTINCT q.client_id) AS active_clients, "
        "       COUNT(DISTINCT c.person_id) AS active_persons, "
        "       COALESCE(AVG(NULLIF(q.elapsed_us, 0)), 0) AS avg_elapsed_us, "
        "       COALESCE(SUM(q.cached), 0) AS cached "
        f"{JOINS}{where}",
        tuple(params),
    ).fetchone()

    total = int(row["total"])
    blocked = int(row["blocked"])
    return {
        "total": total,
        "blocked": blocked,
        "allowed": total - blocked,
        "blocked_percent": round(blocked * 100.0 / total, 2) if total else 0.0,
        "unique_domains": int(row["unique_domains"]),
        "active_clients": int(row["active_clients"]),
        "active_persons": int(row["active_persons"]),
        "cached": int(row["cached"]),
        "avg_response_time_ms": round(float(row["avg_elapsed_us"]) / 1000.0, 2),
        "from_ns": from_ns,
        "to_ns": to_ns,
    }


def _top(
    conn: sqlite3.Connection,
    select: str,
    group_by: str,
    *,
    filter_node: FilterNode | None,
    from_ns: int | None,
    to_ns: int | None,
    limit: int,
    extra_where: str = "",
    extra_joins: str = "",
) -> list[dict[str, Any]]:
    where, params = _where(filter_node, from_ns, to_ns)
    if extra_where:
        where = f"{where} AND {extra_where}" if where else f"WHERE {extra_where}"
    limit = max(1, min(int(limit), MAX_TOP_LIMIT))
    rows = conn.execute(
        f"SELECT {select}, COUNT(*) AS count, COALESCE(SUM(q.blocked), 0) AS blocked "
        f"{JOINS}{extra_joins}{where} "
        f"GROUP BY {group_by} ORDER BY count DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def top_domains(conn: sqlite3.Connection, **kwargs: Any) -> list[dict[str, Any]]:
    limit = kwargs.pop("limit", DEFAULT_TOP_LIMIT)
    return _top(
        conn,
        "d.id AS domain_id, d.name AS domain, d.registrable",
        "d.id",
        limit=limit,
        **kwargs,
    )


def top_blocked_domains(conn: sqlite3.Connection, **kwargs: Any) -> list[dict[str, Any]]:
    limit = kwargs.pop("limit", DEFAULT_TOP_LIMIT)
    return _top(
        conn,
        "d.id AS domain_id, d.name AS domain, d.registrable",
        "d.id",
        limit=limit,
        extra_where="q.blocked = 1",
        **kwargs,
    )


def top_clients(conn: sqlite3.Connection, **kwargs: Any) -> list[dict[str, Any]]:
    limit = kwargs.pop("limit", DEFAULT_TOP_LIMIT)
    return _top(
        conn,
        "c.id AS client_id, c.ip AS client_ip, "
        "COALESCE(NULLIF(c.alias, ''), NULLIF(c.adguard_name, ''), c.ip) AS client_name, "
        "p.name AS person",
        "c.id",
        limit=limit,
        **kwargs,
    )


def top_persons(conn: sqlite3.Connection, **kwargs: Any) -> list[dict[str, Any]]:
    limit = kwargs.pop("limit", DEFAULT_TOP_LIMIT)
    return _top(
        conn,
        "p.id AS person_id, p.name AS person",
        "p.id",
        limit=limit,
        extra_where="p.id IS NOT NULL",
        **kwargs,
    )


def top_query_types(conn: sqlite3.Connection, **kwargs: Any) -> list[dict[str, Any]]:
    limit = kwargs.pop("limit", DEFAULT_TOP_LIMIT)
    return _top(conn, "q.qtype AS query_type", "q.qtype", limit=limit, **kwargs)


def top_upstreams(conn: sqlite3.Connection, **kwargs: Any) -> list[dict[str, Any]]:
    limit = kwargs.pop("limit", DEFAULT_TOP_LIMIT)
    return _top(
        conn,
        "q.upstream",
        "q.upstream",
        limit=limit,
        extra_where="q.upstream <> ''",
        **kwargs,
    )


def _top_tags(conn: sqlite3.Connection, kind: str, **kwargs: Any) -> list[dict[str, Any]]:
    limit = kwargs.pop("limit", DEFAULT_TOP_LIMIT)
    return _top(
        conn,
        "t.id AS tag_id, t.name AS name, t.color AS color",
        "t.id",
        limit=limit,
        extra_joins=(
            "JOIN domain_tags dt ON dt.domain_id = q.domain_id "
            "JOIN tags t ON t.id = dt.tag_id "
        ),
        extra_where="t.kind = " + ("'category'" if kind == "category" else "'tag'"),
        **kwargs,
    )


def top_categories(conn: sqlite3.Connection, **kwargs: Any) -> list[dict[str, Any]]:
    return _top_tags(conn, "category", **kwargs)


def top_tags(conn: sqlite3.Connection, **kwargs: Any) -> list[dict[str, Any]]:
    return _top_tags(conn, "tag", **kwargs)


def pick_bucket_seconds(span_seconds: int, target_buckets: int = 60) -> int:
    """Choose a round bucket width that yields roughly *target_buckets* points."""
    if span_seconds <= 0:
        return BUCKET_STEPS[0]
    ideal = span_seconds / max(1, target_buckets)
    for step in BUCKET_STEPS:
        if step >= ideal:
            return step
    return BUCKET_STEPS[-1]


def timeline(
    conn: sqlite3.Connection,
    *,
    filter_node: FilterNode | None = None,
    from_ns: int | None = None,
    to_ns: int | None = None,
    buckets: int = 60,
) -> dict[str, Any]:
    """Activity over time as ``{bucket_seconds, points: [{t, total, blocked}]}``."""
    end_ns = to_ns if to_ns is not None else now_ns()
    if from_ns is None:
        row = conn.execute("SELECT MIN(ts_ns) AS first FROM queries").fetchone()
        from_ns = int(row["first"] or end_ns - 3600 * NS_PER_SECOND)

    span_seconds = max(1, (end_ns - from_ns) // NS_PER_SECOND)
    bucket_seconds = pick_bucket_seconds(span_seconds, buckets)
    start_seconds = (from_ns // NS_PER_SECOND) // bucket_seconds * bucket_seconds

    if filter_node is None and bucket_seconds >= 60:
        # Rollup path: no join with the queries table at all.
        rows = conn.execute(
            "SELECT (bucket - ?) / ? AS slot, SUM(total) AS total, SUM(blocked) AS blocked "
            "FROM stats_minute WHERE bucket >= ? AND bucket < ? GROUP BY slot ORDER BY slot",
            (
                start_seconds,
                bucket_seconds,
                start_seconds,
                end_ns // NS_PER_SECOND + bucket_seconds,
            ),
        ).fetchall()
        source = "rollup"
    else:
        where, params = _where(filter_node, from_ns, end_ns)
        rows = conn.execute(
            "SELECT (q.ts_ns / ? - ?) / ? AS slot, COUNT(*) AS total, "
            "       COALESCE(SUM(q.blocked), 0) AS blocked "
            f"{JOINS}{where} GROUP BY slot ORDER BY slot",
            (NS_PER_SECOND, start_seconds, bucket_seconds, *params),
        ).fetchall()
        source = "queries"

    by_slot = {int(row["slot"]): (int(row["total"]), int(row["blocked"])) for row in rows}
    slot_count = max(1, min(buckets * 4, int(span_seconds // bucket_seconds) + 1))
    points = []
    for index in range(slot_count):
        total, blocked = by_slot.get(index, (0, 0))
        points.append(
            {
                "t": (start_seconds + index * bucket_seconds) * 1000,
                "total": total,
                "blocked": blocked,
                "allowed": total - blocked,
            }
        )

    return {
        "bucket_seconds": bucket_seconds,
        "from_ns": from_ns,
        "to_ns": end_ns,
        "source": source,
        "points": points,
    }


#: The pieces the dashboard is made of. Each one is an independent query, so
#: the API layer can run them on separate connections in parallel.
PART_BUILDERS: dict[str, Any] = {}


def _register() -> None:
    PART_BUILDERS.update(
        {
            "summary": summary,
            "timeline": timeline,
            "top_domains": top_domains,
            "top_blocked_domains": top_blocked_domains,
            "top_clients": top_clients,
            "top_persons": top_persons,
            "top_categories": top_categories,
            "top_tags": top_tags,
            "top_query_types": top_query_types,
            "top_upstreams": top_upstreams,
        }
    )


_register()

DEFAULT_PARTS: tuple[str, ...] = tuple(PART_BUILDERS)


def build_part(
    conn: sqlite3.Connection,
    part: str,
    *,
    filter_node: FilterNode | None = None,
    from_ns: int | None = None,
    to_ns: int | None = None,
    top_limit: int = DEFAULT_TOP_LIMIT,
    buckets: int = 60,
) -> Any:
    """Compute one dashboard part by name."""
    builder = PART_BUILDERS.get(part)
    if builder is None:
        raise KeyError(part)
    if part == "summary":
        return builder(conn, filter_node=filter_node, from_ns=from_ns, to_ns=to_ns)
    if part == "timeline":
        return builder(
            conn, filter_node=filter_node, from_ns=from_ns, to_ns=to_ns, buckets=buckets
        )
    return builder(
        conn, filter_node=filter_node, from_ns=from_ns, to_ns=to_ns, limit=top_limit
    )


def overview(
    conn: sqlite3.Connection,
    *,
    filter_node: FilterNode | None = None,
    from_ns: int | None = None,
    to_ns: int | None = None,
    top_limit: int = DEFAULT_TOP_LIMIT,
    buckets: int = 60,
    parts: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Every dashboard widget, computed sequentially on one connection.

    The API normally uses :func:`build_part` across several connections so the
    pieces run in parallel; this is the straightforward version used by tests
    and by the detail pages.
    """
    return {
        part: build_part(
            conn,
            part,
            filter_node=filter_node,
            from_ns=from_ns,
            to_ns=to_ns,
            top_limit=top_limit,
            buckets=buckets,
        )
        for part in (parts or DEFAULT_PARTS)
    }
