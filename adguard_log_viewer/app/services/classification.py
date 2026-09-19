"""Applying the categorisation engine to stored domains.

Classification happens **per domain**, not per query. A domain records the rule
set revision it was last classified with; when rules change the revision is
bumped and stale domains are re-classified in the background.

Tags a user attached by hand (``source = 'manual'``) are never touched by an
automatic pass.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Sequence

from app.categorization.engine import CategorizationEngine, TagRef
from app.db.sqlutil import chunked, kv_get, kv_set, placeholders

_LOGGER = logging.getLogger(__name__)

AUTOMATIC_SOURCES = ("builtin", "rule")
RULESET_REV_KEY = "ruleset_rev"


def get_ruleset_rev(conn: sqlite3.Connection) -> int:
    return int(kv_get(conn, "settings", RULESET_REV_KEY, 0) or 0)


def bump_ruleset_rev(conn: sqlite3.Connection) -> int:
    revision = get_ruleset_rev(conn) + 1
    kv_set(conn, "settings", RULESET_REV_KEY, revision)
    return revision


class TagResolver:
    """Resolves ``(name, kind)`` to a tag id, creating tags on demand."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], int] = {}

    def prime(self, conn: sqlite3.Connection) -> None:
        self._cache.clear()
        for row in conn.execute("SELECT id, name, kind FROM tags"):
            self._cache[(row["name"], row["kind"])] = row["id"]

    def resolve(self, conn: sqlite3.Connection, tag: TagRef, *, color: str = "") -> int:
        key = (tag.name, tag.kind)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        conn.execute(
            "INSERT INTO tags (name, kind, color, builtin) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(name, kind) DO NOTHING",
            (tag.name, tag.kind, color),
        )
        row = conn.execute(
            "SELECT id FROM tags WHERE name = ? AND kind = ?", (tag.name, tag.kind)
        ).fetchone()
        tag_id = int(row["id"])
        self._cache[key] = tag_id
        return tag_id

    def resolve_many(
        self, conn: sqlite3.Connection, tags: Iterable[TagRef], colors: dict[str, str] | None = None
    ) -> list[int]:
        colors = colors or {}
        return [self.resolve(conn, tag, color=colors.get(tag.name, "")) for tag in tags]


def seed_tags(
    conn: sqlite3.Connection, tags: Sequence[TagRef], colors: dict[str, str]
) -> None:
    """Insert the built-in tag/category catalogue if it is not there yet."""
    for tag in tags:
        conn.execute(
            "INSERT INTO tags (name, kind, color, builtin) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(name, kind) DO UPDATE SET color = "
            "CASE WHEN tags.color = '' THEN excluded.color ELSE tags.color END",
            (tag.name, tag.kind, colors.get(tag.name, "")),
        )


def classify_domains(
    conn: sqlite3.Connection,
    engine: CategorizationEngine,
    domains: Sequence[tuple[int, str]],
    *,
    revision: int,
    resolver: TagResolver | None = None,
    tag_colors: dict[str, str] | None = None,
) -> int:
    """Re-derive automatic tags for *domains* (``[(id, name), ...]``).

    Returns the number of domains processed.
    """
    if not domains:
        return 0

    resolver = resolver or TagResolver()
    if not resolver._cache:
        resolver.prime(conn)

    ids = [domain_id for domain_id, _ in domains]
    for batch in chunked(ids):
        conn.execute(
            f"DELETE FROM domain_tags WHERE source IN ({placeholders(len(AUTOMATIC_SOURCES))}) "
            f"AND domain_id IN ({placeholders(len(batch))})",
            (*AUTOMATIC_SOURCES, *batch),
        )

    links: list[tuple[int, int, str]] = []
    for domain_id, name in domains:
        for tag in engine.classify(name):
            tag_id = resolver.resolve(conn, tag, color=(tag_colors or {}).get(tag.name, ""))
            links.append((domain_id, tag_id, "builtin"))

    if links:
        conn.executemany(
            "INSERT INTO domain_tags (domain_id, tag_id, source) VALUES (?, ?, ?) "
            "ON CONFLICT(domain_id, tag_id) DO NOTHING",
            links,
        )

    for batch in chunked(ids):
        conn.execute(
            f"UPDATE domains SET ruleset_rev = ? WHERE id IN ({placeholders(len(batch))})",
            (revision, *batch),
        )

    return len(domains)


def stale_domains(
    conn: sqlite3.Connection, *, revision: int, limit: int = 2000
) -> list[tuple[int, str]]:
    """Domains that still carry an older rule set revision."""
    rows = conn.execute(
        "SELECT id, name FROM domains WHERE ruleset_rev <> ? ORDER BY last_seen_ns DESC LIMIT ?",
        (revision, limit),
    ).fetchall()
    return [(int(row["id"]), str(row["name"])) for row in rows]


def count_stale_domains(conn: sqlite3.Connection, *, revision: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM domains WHERE ruleset_rev <> ?", (revision,)
    ).fetchone()
    return int(row["n"])
