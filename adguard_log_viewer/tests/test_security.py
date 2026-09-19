"""Hardening: injection, path traversal, runaway queries and secret exposure."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db.database import Database, QueryTimeout
from app.filters.nodes import MAX_REGEX_LENGTH, FilterError, parse_filter
from app.filters.sql_builder import compile_filter
from app.services.classification import TagResolver
from app.services.ingest_store import store_records
from app.services.query_service import list_queries
from tests.conftest import make_record


def unescape_like(value: str) -> str:
    """Reverse the LIKE escaping the SQL builder applies to a value."""
    out: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            out.append(value[index + 1])
            index += 2
        else:
            out.append(value[index])
            index += 1
    return "".join(out)


INJECTION_PAYLOADS = [
    "'; DROP TABLE queries; --",
    "' OR 1=1 --",
    '" UNION SELECT * FROM settings --',
    "a'); DELETE FROM domains; --",
    "\\'; PRAGMA writable_schema=1; --",
]


class TestSqlInjection:
    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    @pytest.mark.parametrize(
        "field", ["domain", "client_ip", "client_name", "person", "tag", "rule", "upstream"]
    )
    def test_values_never_reach_the_statement_text(self, payload: str, field: str) -> None:
        compiled = compile_filter(
            parse_filter({"field": field, "operator": "contains", "value": payload})
        )
        assert "DROP" not in compiled.sql.upper()
        assert "DELETE" not in compiled.sql.upper()
        assert "UNION" not in compiled.sql.upper()
        assert "PRAGMA" not in compiled.sql.upper()
        # The payload survives as data. LIKE metacharacters inside it are
        # escaped, so undo that before comparing.
        assert [unescape_like(str(param)) for param in compiled.params] == [f"%{payload}%"]

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_the_database_survives_the_query(
        self, db: Database, base_ts: int, payload: str
    ) -> None:
        with db.write() as conn:
            store_records(
                conn, [make_record(ts_ns=base_ts, domain="a.com")], resolver=TagResolver()
            )
        node = parse_filter({"field": "domain", "operator": "contains", "value": payload})
        with db.read() as conn:
            page = list_queries(conn, filter_node=node, limit=10)
            remaining = conn.execute("SELECT COUNT(*) AS n FROM queries").fetchone()["n"]
        assert page.items == []
        assert remaining == 1

    def test_a_sort_key_cannot_be_injected(self, db: Database, base_ts: int) -> None:
        with db.write() as conn:
            store_records(
                conn, [make_record(ts_ns=base_ts, domain="a.com")], resolver=TagResolver()
            )
        with db.read() as conn:
            # An unknown sort falls back to the default instead of being interpolated.
            page = list_queries(conn, sort="q.ts_ns; DROP TABLE queries--", limit=10)
            remaining = conn.execute("SELECT COUNT(*) AS n FROM queries").fetchone()["n"]
        assert len(page.items) == 1
        assert remaining == 1


class TestRegexGuards:
    def test_an_oversized_pattern_is_rejected(self) -> None:
        with pytest.raises(FilterError, match="longer than"):
            parse_filter(
                {"field": "domain", "operator": "regex", "value": "a" * (MAX_REGEX_LENGTH + 1)}
            )

    def test_a_pattern_at_the_limit_is_accepted(self) -> None:
        assert parse_filter(
            {"field": "domain", "operator": "regex", "value": "a" * MAX_REGEX_LENGTH}
        )

    def test_an_invalid_pattern_matches_nothing(self, db: Database, base_ts: int) -> None:
        with db.write() as conn:
            store_records(
                conn, [make_record(ts_ns=base_ts, domain="a.com")], resolver=TagResolver()
            )
        node = parse_filter({"field": "domain", "operator": "regex", "value": "(((["})
        with db.read() as conn:
            assert list_queries(conn, filter_node=node, limit=10).items == []


class TestQueryTimeout:
    def test_a_long_read_is_aborted(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "slow.db", read_timeout=0.1)
        database.connect()
        with database.write() as conn:
            conn.execute("CREATE TABLE numbers (value INTEGER)")

        # A recursive CTE with no bound: the progress handler is what stops it,
        # which is exactly the protection being tested.
        with pytest.raises(QueryTimeout, match="still running"), database.read() as conn:
            conn.execute(
                "WITH RECURSIVE forever(x) AS "
                "(SELECT 1 UNION ALL SELECT x + 1 FROM forever) "
                "SELECT COUNT(*) FROM forever"
            ).fetchone()
        database.close()

    def test_normal_reads_are_unaffected(self, db: Database, base_ts: int) -> None:
        with db.write() as conn:
            store_records(
                conn, [make_record(ts_ns=base_ts, domain="a.com")], resolver=TagResolver()
            )
        with db.read() as conn:
            assert list_queries(conn, limit=10).total == 1

    def test_other_operational_errors_still_propagate(self, db: Database) -> None:
        with pytest.raises(sqlite3.OperationalError), db.read() as conn:
            conn.execute("SELECT * FROM a_table_that_does_not_exist")


class TestStaticFileServing:
    @pytest.mark.parametrize(
        "path",
        [
            "../../../etc/passwd",
            "..%2f..%2fetc%2fpasswd",
            "assets/../../../../etc/hosts",
            "....//....//etc/passwd",
        ],
    )
    def test_traversal_attempts_fall_back_to_the_app_shell(self, bare_client, path: str) -> None:
        response = bare_client.get(f"/{path}")
        assert response.status_code == 200
        assert "root:" not in response.text
        assert "text/html" in response.headers["content-type"]
