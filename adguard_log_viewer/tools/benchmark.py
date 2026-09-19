#!/usr/bin/env python3
"""Load a synthetic query log and time the paths the UI depends on.

    python tools/benchmark.py --records 1000000

Generates a realistic mix of domains, clients and outcomes, then measures
ingest throughput, the filtered listing, the dashboard aggregation and the
retention cleanup. Nothing here touches the real database.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import shutil
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.common.timeutil import NS_PER_SECOND, now_ns
from app.db.database import Database
from app.db.migrations import migrate
from app.db.sqlutil import kv_set
from app.filters.nodes import parse_filter, quick_search_filter
from app.ingest.records import DnsAnswer, QueryRecord
from app.services import dashboard_service
from app.services.classification import TagResolver
from app.services.ingest_store import store_records
from app.services.query_service import list_queries
from app.services.retention import cleanup
from app.services.rules_service import (
    build_engine,
    builtin_tag_colors,
    seed_builtin_tags,
)

POPULAR_DOMAINS = [
    "www.youtube.com", "i.ytimg.com", "googlevideo.com", "www.google.com",
    "clients4.google.com", "graph.facebook.com", "www.instagram.com", "api.tiktokv.com",
    "doubleclick.net", "googlesyndication.com", "google-analytics.com", "adnxs.com",
    "netflix.com", "nflxvideo.net", "open.spotify.com", "api.spotify.com",
    "vortex.data.microsoft.com", "windowsupdate.com", "push.apple.com", "gs.apple.com",
    "index.hu", "telex.hu", "444.hu", "port.hu", "otpbank.hu",
    "shelly.cloud", "tuya.com", "home-assistant.io", "pool.ntp.org",
    "steampowered.com", "discord.com", "claude.ai", "chatgpt.com",
    "github.com", "raw.githubusercontent.com", "pypi.org", "cloudflare.com",
]

QUERY_TYPES = ["A", "A", "A", "AAAA", "AAAA", "HTTPS", "PTR", "CNAME", "SVCB", "TXT"]

REASONS = (
    [""] * 80
    + ["FilteredBlackList"] * 12
    + ["NotFilteredWhiteList"] * 3
    + ["FilteredSafeBrowsing"] * 2
    + ["RewriteRule"] * 2
    + ["FilteredBlockedService"] * 1
)


def generate(count: int, clients: int, seed: int = 7) -> Iterator[QueryRecord]:
    rng = random.Random(seed)
    end = now_ns()
    start = end - 30 * 86_400 * NS_PER_SECOND
    step = max(1, (end - start) // max(1, count))

    ips = [f"192.168.1.{index + 10}" for index in range(clients)]
    names = [f"device-{index:02d}" for index in range(clients)]

    for index in range(count):
        if rng.random() < 0.25:
            # Long-tail traffic: a subdomain nobody has seen before.
            domain = (
                f"r{rng.randrange(1, 900)}.cdn{rng.randrange(1, 60)}"
                f".example{rng.randrange(1, 40)}.net"
            )
        else:
            domain = rng.choice(POPULAR_DOMAINS)
        client = rng.randrange(clients)
        reason = rng.choice(REASONS)
        yield QueryRecord(
            ts_ns=start + index * step + rng.randrange(0, max(1, step)),
            domain=domain,
            client_ip=ips[client],
            client_name=names[client],
            qtype=rng.choice(QUERY_TYPES),
            status="NOERROR",
            reason=reason,
            elapsed_us=rng.randrange(200, 90_000),
            upstream=rng.choice(["https://dns.quad9.net", "tls://1.1.1.1", "8.8.8.8:53"]),
            answers=[DnsAnswer(type="A", value="93.184.216.34", ttl=300)],
        )


async def _parallel_overview(database: Database, from_ns: int) -> dict[str, Any]:
    """Same shape as the /api/dashboard endpoint: one read connection per part."""

    async def part(name: str) -> tuple[str, Any]:
        value = await database.run_read(
            lambda conn: dashboard_service.build_part(conn, name, from_ns=from_ns)
        )
        return name, value

    results = await asyncio.gather(*(part(name) for name in dashboard_service.DEFAULT_PARTS))
    return dict(results)


def timed(label: str, fn: Callable[[], Any], repeat: int = 3) -> Any:
    durations: list[float] = []
    result: Any = None
    for _ in range(repeat):
        started = time.perf_counter()
        result = fn()
        durations.append((time.perf_counter() - started) * 1000)
    best = min(durations)
    median = statistics.median(durations)
    flag = "  <-- SLOW" if median > 400 else ""
    print(f"  {label:<46} {best:8.1f} ms best   {median:8.1f} ms median{flag}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=250_000)
    parser.add_argument("--clients", type=int, default=25)
    parser.add_argument("--batch", type=int, default=5_000)
    parser.add_argument("--keep", action="store_true", help="keep the generated database")
    args = parser.parse_args()

    workdir = Path(tempfile.mkdtemp(prefix="aglv-bench-"))
    db_path = workdir / "benchmark.db"
    database = Database(db_path)
    database.connect()
    migrate(database.write_connection)
    with database.write() as conn:
        seed_builtin_tags(conn)
        kv_set(conn, "settings", "ruleset_rev", 1)
    with database.read() as conn:
        engine = build_engine(conn)
    colors = builtin_tag_colors()

    print(f"Generating and ingesting {args.records:,} records "
          f"across {args.clients} clients...")
    resolver = TagResolver()
    inserted = 0
    started = time.perf_counter()
    batch: list[QueryRecord] = []
    for record in generate(args.records, args.clients):
        batch.append(record)
        if len(batch) >= args.batch:
            with database.write() as conn:
                inserted += store_records(
                    conn, batch, engine=engine, revision=1, resolver=resolver, tag_colors=colors
                ).inserted
            batch.clear()
    if batch:
        with database.write() as conn:
            inserted += store_records(
                conn, batch, engine=engine, revision=1, resolver=resolver, tag_colors=colors
            ).inserted
    ingest_seconds = time.perf_counter() - started

    size_mb = db_path.stat().st_size / 1024 / 1024
    with database.read() as conn:
        domains = conn.execute("SELECT COUNT(*) AS n FROM domains").fetchone()["n"]
        tags = conn.execute("SELECT COUNT(*) AS n FROM domain_tags").fetchone()["n"]

    print(
        f"\nIngest: {inserted:,} rows in {ingest_seconds:.1f}s "
        f"({inserted / max(ingest_seconds, 0.001):,.0f} rows/s)\n"
        f"Database: {size_mb:.1f} MB, {domains:,} domains, {tags:,} domain-tag links\n"
    )

    print("Query paths (what the UI actually calls):")
    with database.read() as conn:
        timed("first page, no filter", lambda: list_queries(conn, limit=100))
        timed(
            "ANY search: googl / youtube / googlevideo",
            lambda: list_queries(
                conn,
                filter_node=quick_search_filter(
                    ["googl", "youtube", "googlevideo"], mode="any", fields=("domain",)
                ),
                limit=100,
            ),
        )
        timed(
            "nested AND/OR + 24h window",
            lambda: list_queries(
                conn,
                filter_node=parse_filter(
                    {
                        "op": "and",
                        "children": [
                            {
                                "op": "or",
                                "children": [
                                    {"field": "domain", "operator": "contains",
                                     "value": "youtube"},
                                    {"field": "domain", "operator": "contains",
                                     "value": "googlevideo"},
                                ],
                            },
                            {"field": "client_ip", "operator": "equals", "value": "192.168.1.10"},
                            {"field": "timestamp", "operator": "gte", "value": "now-24h"},
                        ],
                    }
                ),
                limit=100,
            ),
        )
        timed(
            "category = Advertising",
            lambda: list_queries(
                conn,
                filter_node=parse_filter(
                    {"field": "category", "operator": "equals", "value": "Advertising"}
                ),
                limit=100,
            ),
        )
        timed(
            "blocked only, last 7 days",
            lambda: list_queries(
                conn,
                filter_node=parse_filter(
                    [
                        {"field": "blocked", "operator": "equals", "value": True},
                        {"field": "timestamp", "operator": "gte", "value": "now-7d"},
                    ]
                ),
                limit=100,
            ),
        )
        timed(
            "regex on domain",
            lambda: list_queries(
                conn,
                filter_node=parse_filter(
                    {"field": "domain", "operator": "regex", "value": r"^r\d+\.cdn\d+\."}
                ),
                limit=100,
                include_total=False,
            ),
        )
        timed("deep page (offset 10000)", lambda: list_queries(conn, limit=100, offset=10_000))

        print("\nDashboard:")
        timed(
            "overview, 24h",
            lambda: dashboard_service.overview(
                conn, from_ns=now_ns() - 86_400 * NS_PER_SECOND
            ),
        )
        timed(
            "overview, 7d",
            lambda: dashboard_service.overview(
                conn, from_ns=now_ns() - 7 * 86_400 * NS_PER_SECOND
            ),
        )
        timed(
            "timeline, 30d (rollup path)",
            lambda: dashboard_service.timeline(
                conn, from_ns=now_ns() - 30 * 86_400 * NS_PER_SECOND
            ),
        )

    print("\nDashboard via the API path (parts run in parallel):")
    for label, span in (("24h", 86_400), ("7d", 7 * 86_400)):
        timed(
            f"overview, {label}",
            lambda span=span: asyncio.run(
                _parallel_overview(database, now_ns() - span * NS_PER_SECOND)
            ),
        )

    print("\nMaintenance:")
    started = time.perf_counter()
    with database.write() as conn:
        result = cleanup(conn, 7)
    print(
        f"  retention cleanup to 7 days: removed {result.deleted_queries:,} rows "
        f"in {(time.perf_counter() - started):.1f}s"
    )

    database.close()
    if args.keep:
        print(f"\nDatabase kept at {db_path}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
