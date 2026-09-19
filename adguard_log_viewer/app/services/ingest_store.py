"""Writing normalised query records into SQLite.

The batch is written in one transaction and does four things:

1. resolves the batch's domains and clients to ids, inserting the new ones;
2. skips records already present (checked by ``uid``, so restarting the add-on
   or re-reading an overlapping API page never double-counts anything);
3. inserts the queries;
4. updates the aggregate counters and the per-minute activity rollup.

Counters are only advanced for rows that were genuinely inserted, which is why
existing ``uid``s are looked up rather than relying on ``INSERT OR IGNORE``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.categorization.engine import CategorizationEngine
from app.common.domains import registrable_domain
from app.common.timeutil import minute_bucket
from app.db.sqlutil import chunked, placeholders
from app.ingest.records import QueryRecord
from app.services.classification import TagResolver, classify_domains

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestStats:
    received: int = 0
    inserted: int = 0
    duplicates: int = 0
    new_domains: int = 0
    new_clients: int = 0
    first_id: int = 0
    last_id: int = 0
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: IngestStats) -> None:
        self.received += other.received
        self.inserted += other.inserted
        self.duplicates += other.duplicates
        self.new_domains += other.new_domains
        self.new_clients += other.new_clients
        self.last_id = max(self.last_id, other.last_id)
        self.first_id = self.first_id or other.first_id

    def as_dict(self) -> dict[str, object]:
        return {
            "received": self.received,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "new_domains": self.new_domains,
            "new_clients": self.new_clients,
            "last_id": self.last_id,
        }


def _existing_uids(conn: sqlite3.Connection, uids: Sequence[int]) -> set[int]:
    found: set[int] = set()
    for batch in chunked(uids):
        rows = conn.execute(
            f"SELECT uid FROM queries WHERE uid IN ({placeholders(len(batch))})", tuple(batch)
        ).fetchall()
        found.update(int(row["uid"]) for row in rows)
    return found


def _resolve_domains(
    conn: sqlite3.Connection, records: Sequence[QueryRecord]
) -> tuple[dict[str, int], list[tuple[int, str]]]:
    """Insert unseen domains and return ``{name: id}`` plus the new ones."""
    bounds: dict[str, tuple[int, int]] = {}
    for record in records:
        low, high = bounds.get(record.domain, (record.ts_ns, record.ts_ns))
        bounds[record.domain] = (min(low, record.ts_ns), max(high, record.ts_ns))

    names = list(bounds)
    existing: set[str] = set()
    for batch in chunked(names):
        rows = conn.execute(
            f"SELECT name FROM domains WHERE name IN ({placeholders(len(batch))})", tuple(batch)
        ).fetchall()
        existing.update(str(row["name"]) for row in rows)

    conn.executemany(
        "INSERT INTO domains (name, registrable, first_seen_ns, last_seen_ns, ruleset_rev) "
        "VALUES (?, ?, ?, ?, -1) "
        "ON CONFLICT(name) DO UPDATE SET "
        "  first_seen_ns = MIN(domains.first_seen_ns, excluded.first_seen_ns), "
        "  last_seen_ns = MAX(domains.last_seen_ns, excluded.last_seen_ns)",
        [
            (name, registrable_domain(name), low, high)
            for name, (low, high) in bounds.items()
        ],
    )

    mapping: dict[str, int] = {}
    for batch in chunked(names):
        rows = conn.execute(
            f"SELECT id, name FROM domains WHERE name IN ({placeholders(len(batch))})",
            tuple(batch),
        ).fetchall()
        for row in rows:
            mapping[str(row["name"])] = int(row["id"])

    new_domains = [(mapping[name], name) for name in names if name not in existing]
    return mapping, new_domains


def _resolve_clients(
    conn: sqlite3.Connection, records: Sequence[QueryRecord]
) -> tuple[dict[str, int], int]:
    bounds: dict[str, tuple[int, int]] = {}
    names: dict[str, str] = {}
    for record in records:
        low, high = bounds.get(record.client_ip, (record.ts_ns, record.ts_ns))
        bounds[record.client_ip] = (min(low, record.ts_ns), max(high, record.ts_ns))
        if record.client_name:
            names[record.client_ip] = record.client_name

    ips = list(bounds)
    existing: set[str] = set()
    for batch in chunked(ips):
        rows = conn.execute(
            f"SELECT ip FROM clients WHERE ip IN ({placeholders(len(batch))})", tuple(batch)
        ).fetchall()
        existing.update(str(row["ip"]) for row in rows)

    conn.executemany(
        "INSERT INTO clients (ip, adguard_name, first_seen_ns, last_seen_ns) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(ip) DO UPDATE SET "
        "  first_seen_ns = MIN(clients.first_seen_ns, excluded.first_seen_ns), "
        "  last_seen_ns = MAX(clients.last_seen_ns, excluded.last_seen_ns), "
        "  adguard_name = CASE WHEN excluded.adguard_name <> '' "
        "                      THEN excluded.adguard_name ELSE clients.adguard_name END",
        [(ip, names.get(ip, ""), low, high) for ip, (low, high) in bounds.items()],
    )

    mapping: dict[str, int] = {}
    for batch in chunked(ips):
        rows = conn.execute(
            f"SELECT id, ip FROM clients WHERE ip IN ({placeholders(len(batch))})", tuple(batch)
        ).fetchall()
        for row in rows:
            mapping[str(row["ip"])] = int(row["id"])

    return mapping, len(ips) - len(existing)


def store_records(
    conn: sqlite3.Connection,
    records: Sequence[QueryRecord],
    *,
    engine: CategorizationEngine | None = None,
    revision: int = 0,
    resolver: TagResolver | None = None,
    tag_colors: dict[str, str] | None = None,
) -> IngestStats:
    """Persist a batch of records. Must run inside a write transaction."""
    stats = IngestStats(received=len(records))
    if not records:
        return stats

    # Collapse duplicates inside the batch itself first.
    unique: dict[int, QueryRecord] = {}
    for record in records:
        if record.is_valid():
            unique[record.uid] = record
    stats.duplicates += len(records) - len(unique)

    uids = list(unique)
    known = _existing_uids(conn, uids)
    fresh = [record for uid, record in unique.items() if uid not in known]
    stats.duplicates += len(known)
    if not fresh:
        return stats

    domain_ids, new_domains = _resolve_domains(conn, fresh)
    client_ids, new_client_count = _resolve_clients(conn, fresh)
    stats.new_domains = len(new_domains)
    stats.new_clients = new_client_count

    rows = []
    domain_counts: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    client_counts: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    minute_counts: dict[int, list[int]] = defaultdict(lambda: [0, 0])

    for record in fresh:
        domain_id = domain_ids[record.domain]
        client_id = client_ids[record.client_ip]
        blocked = 1 if record.blocked else 0
        rows.append(
            (
                record.uid,
                record.ts_ns,
                domain_id,
                client_id,
                record.qtype,
                record.qclass,
                record.status,
                record.reason,
                blocked,
                record.rule_text,
                record.filter_list_id,
                record.elapsed_us,
                record.upstream,
                1 if record.cached else 0,
                record.primary_answer,
                json.dumps([answer.as_dict() for answer in record.answers], separators=(",", ":"))
                if record.answers
                else "",
                record.client_proto,
            )
        )

        counters = domain_counts[domain_id]
        counters[0] += 1
        counters[1] += blocked
        counters = client_counts[client_id]
        counters[0] += 1
        counters[1] += blocked
        bucket = minute_counts[minute_bucket(record.ts_ns)]
        bucket[0] += 1
        bucket[1] += blocked

    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO queries "
        "(uid, ts_ns, domain_id, client_id, qtype, qclass, status, reason, blocked, "
        " rule_text, filter_list_id, elapsed_us, upstream, cached, answer, answers_json, "
        " client_proto) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    stats.inserted = conn.total_changes - before
    stats.duplicates += len(rows) - stats.inserted

    row = conn.execute("SELECT MAX(id) AS last FROM queries").fetchone()
    stats.last_id = int(row["last"] or 0)

    conn.executemany(
        "UPDATE domains SET query_count = query_count + ?, blocked_count = blocked_count + ? "
        "WHERE id = ?",
        [(counts[0], counts[1], domain_id) for domain_id, counts in domain_counts.items()],
    )
    conn.executemany(
        "UPDATE clients SET query_count = query_count + ?, blocked_count = blocked_count + ? "
        "WHERE id = ?",
        [(counts[0], counts[1], client_id) for client_id, counts in client_counts.items()],
    )
    conn.executemany(
        "INSERT INTO stats_minute (bucket, total, blocked) VALUES (?, ?, ?) "
        "ON CONFLICT(bucket) DO UPDATE SET "
        "  total = stats_minute.total + excluded.total, "
        "  blocked = stats_minute.blocked + excluded.blocked",
        [(bucket, counts[0], counts[1]) for bucket, counts in minute_counts.items()],
    )

    if engine is not None and new_domains:
        classify_domains(
            conn,
            engine,
            new_domains,
            revision=revision,
            resolver=resolver,
            tag_colors=tag_colors,
        )

    return stats


def apply_client_names(conn: sqlite3.Connection, names: dict[str, str]) -> int:
    """Store the client names AdGuard knows about, without clobbering aliases."""
    if not names:
        return 0
    before = conn.total_changes
    conn.executemany(
        "UPDATE clients SET adguard_name = ? WHERE ip = ? AND adguard_name <> ?",
        [(name, ip, name) for ip, name in names.items()],
    )
    return conn.total_changes - before
