"""Schema migrations.

Every migration is a ``(version, name, statements)`` triple applied in order
inside one transaction, with ``PRAGMA user_version`` acting as the bookkeeping.
Migrations are append-only: never edit a released one, add a new one instead.
That keeps upgrades of an installed app lossless.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence

_LOGGER = logging.getLogger(__name__)

_V1 = """
CREATE TABLE persons (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    color       TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE clients (
    id            INTEGER PRIMARY KEY,
    ip            TEXT    NOT NULL UNIQUE,
    adguard_name  TEXT    NOT NULL DEFAULT '',
    alias         TEXT    NOT NULL DEFAULT '',
    person_id     INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    first_seen_ns INTEGER NOT NULL DEFAULT 0,
    last_seen_ns  INTEGER NOT NULL DEFAULT 0,
    query_count   INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_clients_person ON clients(person_id);

CREATE TABLE domains (
    id            INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL UNIQUE,
    registrable   TEXT    NOT NULL DEFAULT '',
    first_seen_ns INTEGER NOT NULL DEFAULT 0,
    last_seen_ns  INTEGER NOT NULL DEFAULT 0,
    query_count   INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    ruleset_rev   INTEGER NOT NULL DEFAULT -1
);
CREATE INDEX idx_domains_registrable ON domains(registrable);
CREATE INDEX idx_domains_ruleset_rev ON domains(ruleset_rev);

CREATE TABLE tags (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    kind        TEXT    NOT NULL DEFAULT 'tag',
    color       TEXT    NOT NULL DEFAULT '',
    description TEXT    NOT NULL DEFAULT '',
    builtin     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (name, kind)
);

CREATE TABLE domain_tags (
    domain_id INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags(id)    ON DELETE CASCADE,
    source    TEXT    NOT NULL DEFAULT 'rule',
    PRIMARY KEY (domain_id, tag_id)
) WITHOUT ROWID;
CREATE INDEX idx_domain_tags_tag ON domain_tags(tag_id);

CREATE TABLE queries (
    id             INTEGER PRIMARY KEY,
    uid            INTEGER NOT NULL,
    ts_ns          INTEGER NOT NULL,
    domain_id      INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    client_id      INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    qtype          TEXT    NOT NULL DEFAULT '',
    qclass         TEXT    NOT NULL DEFAULT 'IN',
    status         TEXT    NOT NULL DEFAULT '',
    reason         TEXT    NOT NULL DEFAULT '',
    blocked        INTEGER NOT NULL DEFAULT 0,
    rule_text      TEXT    NOT NULL DEFAULT '',
    filter_list_id INTEGER NOT NULL DEFAULT -1,
    elapsed_us     INTEGER NOT NULL DEFAULT 0,
    upstream       TEXT    NOT NULL DEFAULT '',
    cached         INTEGER NOT NULL DEFAULT 0,
    answer         TEXT    NOT NULL DEFAULT '',
    answers_json   TEXT    NOT NULL DEFAULT '',
    client_proto   TEXT    NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX idx_queries_uid ON queries(uid);
CREATE INDEX idx_queries_ts ON queries(ts_ns);
CREATE INDEX idx_queries_domain_ts ON queries(domain_id, ts_ns);
CREATE INDEX idx_queries_client_ts ON queries(client_id, ts_ns);
CREATE INDEX idx_queries_blocked_ts ON queries(blocked, ts_ns);

-- Pre-aggregated activity timeline. Filling this at ingest time keeps the
-- dashboard timeline O(buckets) instead of O(queries).
CREATE TABLE stats_minute (
    bucket  INTEGER PRIMARY KEY,
    total   INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID;

CREATE TABLE rules (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    enabled         INTEGER NOT NULL DEFAULT 1,
    priority        INTEGER NOT NULL DEFAULT 100,
    match_mode      TEXT    NOT NULL DEFAULT 'any',
    conditions_json TEXT    NOT NULL DEFAULT '[]',
    tags_json       TEXT    NOT NULL DEFAULT '[]',
    builtin         INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL DEFAULT 0,
    updated_at      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_rules_priority ON rules(priority, id);

CREATE TABLE saved_filters (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT    NOT NULL DEFAULT '',
    filter_json TEXT    NOT NULL,
    created_at  INTEGER NOT NULL DEFAULT 0,
    updated_at  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE ingest_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
"""


MIGRATIONS: Sequence[tuple[int, str, str]] = (
    (1, "initial schema", _V1),
)


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def target_version() -> int:
    return max(version for version, _, _ in MIGRATIONS) if MIGRATIONS else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every pending migration. Returns the resulting schema version."""
    version = current_version(conn)
    applied = 0
    for number, name, sql in MIGRATIONS:
        if number <= version:
            continue
        _LOGGER.info("Applying migration %d (%s)", number, name)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.executescript(sql)
            # executescript() commits the open transaction before running, so
            # set the version separately and commit it explicitly.
            conn.execute(f"PRAGMA user_version = {number}")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            if conn.in_transaction:
                conn.execute("COMMIT")
        version = number
        applied += 1
    if applied:
        _LOGGER.info("Database schema is now at version %d", version)
    return version
