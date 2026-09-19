"""Retention: dropping history the user no longer wants to keep.

The counters on ``domains`` and ``clients`` have to stay truthful after a
cleanup. Recomputing them from scratch is not an option — a correlated
``SELECT COUNT(*)`` per domain costs about half a millisecond, which on a
database with tens of thousands of domains means a minute of held write lock.

So the cleanup works on **deltas** instead: it reads the batch it is about to
delete, aggregates the per-domain and per-client counts in Python, deletes the
rows, and decrements. That is O(deleted rows), not O(all domains). Only
``first_seen_ns`` needs a second look, and that is answered for every affected
domain at once by a single grouped query per 900 ids.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from app.common.timeutil import NS_PER_SECOND, now_ns
from app.db.sqlutil import chunked, placeholders

_LOGGER = logging.getLogger(__name__)

#: Rows handled per pass. Small enough that one pass is a few hundred
#: milliseconds, large enough that a big backlog drains quickly.
DELETE_CHUNK = 20_000

#: Upper bound on one cleanup call, so a first run against a long history
#: cannot hold the write lock for minutes. Whatever is left is removed by the
#: next scheduled cleanup.
MAX_ROWS_PER_RUN = 500_000


@dataclass(slots=True)
class CleanupResult:
    deleted_queries: int = 0
    deleted_buckets: int = 0
    removed_domains: int = 0
    removed_clients: int = 0
    cutoff_ns: int = 0
    #: True when the run hit :data:`MAX_ROWS_PER_RUN` and more remains.
    more_pending: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "deleted_queries": self.deleted_queries,
            "deleted_buckets": self.deleted_buckets,
            "removed_domains": self.removed_domains,
            "removed_clients": self.removed_clients,
            "cutoff_ns": self.cutoff_ns,
            "more_pending": self.more_pending,
        }


def cutoff_for(retention_days: int, *, reference_ns: int | None = None) -> int | None:
    """Timestamp before which records may be deleted. ``None`` = keep forever."""
    if retention_days <= 0:
        return None
    reference = reference_ns if reference_ns is not None else now_ns()
    return reference - retention_days * 86_400 * NS_PER_SECOND


def _apply_deltas(
    conn: sqlite3.Connection, table: str, deltas: dict[int, tuple[int, int]]
) -> None:
    if not deltas:
        return
    conn.executemany(
        f"UPDATE {table} SET query_count = MAX(0, query_count - ?), "
        "blocked_count = MAX(0, blocked_count - ?) WHERE id = ?",
        [(total, blocked, row_id) for row_id, (total, blocked) in deltas.items()],
    )


def _refresh_first_seen(conn: sqlite3.Connection, table: str, column: str, ids: set[int]) -> None:
    """Set ``first_seen_ns`` from what is left, for the affected rows only.

    One grouped query per 900 ids; the ``(fk, ts_ns)`` index makes each group's
    ``MIN`` a single index seek.
    """
    if not ids:
        return
    ordered = sorted(ids)
    for batch in chunked(ordered):
        rows = conn.execute(
            f"SELECT {column} AS ref, MIN(ts_ns) AS first_ns FROM queries "
            f"WHERE {column} IN ({placeholders(len(batch))}) GROUP BY {column}",
            tuple(batch),
        ).fetchall()
        if rows:
            conn.executemany(
                f"UPDATE {table} SET first_seen_ns = ? WHERE id = ?",
                [(int(row["first_ns"]), int(row["ref"])) for row in rows],
            )


def cleanup(
    conn: sqlite3.Connection,
    retention_days: int,
    *,
    reference_ns: int | None = None,
    prune_empty: bool = True,
    max_rows: int = MAX_ROWS_PER_RUN,
) -> CleanupResult:
    """Delete queries older than the retention window and fix up the counters.

    Must run inside a write transaction.
    """
    result = CleanupResult()
    cutoff = cutoff_for(retention_days, reference_ns=reference_ns)
    if cutoff is None:
        return result
    result.cutoff_ns = cutoff

    domain_ids: set[int] = set()
    client_ids: set[int] = set()

    while result.deleted_queries < max_rows:
        rows = conn.execute(
            "SELECT id, domain_id, client_id, blocked FROM queries "
            "WHERE ts_ns < ? ORDER BY ts_ns LIMIT ?",
            (cutoff, min(DELETE_CHUNK, max_rows - result.deleted_queries)),
        ).fetchall()
        if not rows:
            break

        domain_deltas: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        client_deltas: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        ids: list[int] = []
        for row in rows:
            ids.append(int(row["id"]))
            blocked = int(row["blocked"])
            counters = domain_deltas[int(row["domain_id"])]
            counters[0] += 1
            counters[1] += blocked
            counters = client_deltas[int(row["client_id"])]
            counters[0] += 1
            counters[1] += blocked

        for batch in chunked(ids):
            conn.execute(
                f"DELETE FROM queries WHERE id IN ({placeholders(len(batch))})", tuple(batch)
            )

        _apply_deltas(conn, "domains", {k: (v[0], v[1]) for k, v in domain_deltas.items()})
        _apply_deltas(conn, "clients", {k: (v[0], v[1]) for k, v in client_deltas.items()})
        domain_ids.update(domain_deltas)
        client_ids.update(client_deltas)

        result.deleted_queries += len(ids)
        if len(ids) < DELETE_CHUNK:
            break
    else:
        remaining = conn.execute(
            "SELECT 1 FROM queries WHERE ts_ns < ? LIMIT 1", (cutoff,)
        ).fetchone()
        result.more_pending = remaining is not None

    cursor = conn.execute("DELETE FROM stats_minute WHERE bucket < ?", (cutoff // NS_PER_SECOND,))
    result.deleted_buckets = cursor.rowcount or 0

    if result.deleted_queries:
        _refresh_first_seen(conn, "domains", "domain_id", domain_ids)
        _refresh_first_seen(conn, "clients", "client_id", client_ids)

        if prune_empty:
            cursor = conn.execute("DELETE FROM domains WHERE query_count = 0")
            result.removed_domains = cursor.rowcount or 0
            # Clients are kept when the user gave them an alias or a person, so
            # that naming work is not lost during a quiet period.
            cursor = conn.execute(
                "DELETE FROM clients WHERE query_count = 0 AND alias = '' AND person_id IS NULL"
            )
            result.removed_clients = cursor.rowcount or 0

        _LOGGER.info(
            "Retention cleanup removed %d queries older than %d day(s)%s",
            result.deleted_queries,
            retention_days,
            " (more pending)" if result.more_pending else "",
        )
    return result
