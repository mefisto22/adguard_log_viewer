"""Ingest: deduplication, counters, checkpoints and provider paging."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.categorization.engine import CategorizationEngine
from app.db.database import Database
from app.ingest.api_provider import AdGuardApiQueryLogProvider
from app.ingest.file_provider import AdGuardFileQueryLogProvider
from app.ingest.records import compute_uid
from app.services.classification import TagResolver
from app.services.ingest_store import apply_client_names, store_records
from tests.conftest import make_record, querylog_line


def _store(db: Database, records: list[Any], engine: CategorizationEngine | None = None) -> Any:
    with db.write() as conn:
        return store_records(
            conn, records, engine=engine, revision=1, resolver=TagResolver(), tag_colors={}
        )


class TestDeduplication:
    def test_identical_records_are_stored_once(self, db: Database, base_ts: int) -> None:
        record = make_record(ts_ns=base_ts, domain="example.com")
        first = _store(db, [record])
        second = _store(db, [record])

        assert first.inserted == 1
        assert second.inserted == 0
        assert second.duplicates == 1
        with db.read() as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM queries").fetchone()["n"] == 1

    def test_duplicates_inside_one_batch_collapse(self, db: Database, base_ts: int) -> None:
        record = make_record(ts_ns=base_ts, domain="example.com")
        stats = _store(db, [record, record, record])
        assert stats.received == 3
        assert stats.inserted == 1
        assert stats.duplicates == 2

    def test_overlapping_pages_do_not_double_count(self, db: Database, base_ts: int) -> None:
        page_one = [make_record(ts_ns=base_ts + i, domain=f"d{i}.com") for i in range(10)]
        page_two = [make_record(ts_ns=base_ts + i, domain=f"d{i}.com") for i in range(5, 15)]

        _store(db, page_one)
        _store(db, page_two)

        with db.read() as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM queries").fetchone()["n"] == 15

    def test_uid_distinguishes_the_four_identity_fields(self) -> None:
        base = compute_uid(1000, "10.0.0.1", "a.com", "A")
        assert base != compute_uid(1001, "10.0.0.1", "a.com", "A")
        assert base != compute_uid(1000, "10.0.0.2", "a.com", "A")
        assert base != compute_uid(1000, "10.0.0.1", "b.com", "A")
        assert base != compute_uid(1000, "10.0.0.1", "a.com", "AAAA")
        assert base == compute_uid(1000, "10.0.0.1", "a.com", "A")

    def test_uid_fits_in_a_signed_64_bit_column(self, db: Database) -> None:
        uid = compute_uid(2**62, "10.0.0.1", "x" * 200, "HTTPS")
        assert -(2**63) <= uid < 2**63
        with db.write() as conn:
            conn.execute(
                "INSERT INTO domains (name) VALUES ('x.com')",
            )
            conn.execute("INSERT INTO clients (ip) VALUES ('10.0.0.1')")
            conn.execute(
                "INSERT INTO queries (uid, ts_ns, domain_id, client_id) VALUES (?, 1, 1, 1)",
                (uid,),
            )
        with db.read() as conn:
            assert conn.execute("SELECT uid FROM queries").fetchone()["uid"] == uid


class TestCounters:
    def test_counters_follow_inserted_rows_only(self, db: Database, base_ts: int) -> None:
        records = [
            make_record(ts_ns=base_ts + 1, domain="a.com", client_ip="10.0.0.1"),
            make_record(ts_ns=base_ts + 2, domain="a.com", client_ip="10.0.0.1",
                        reason="FilteredBlackList"),
            make_record(ts_ns=base_ts + 3, domain="b.com", client_ip="10.0.0.2"),
        ]
        _store(db, records)
        _store(db, records)  # replay must not move the counters

        with db.read() as conn:
            domains = {
                row["name"]: (row["query_count"], row["blocked_count"])
                for row in conn.execute("SELECT name, query_count, blocked_count FROM domains")
            }
            clients = {
                row["ip"]: (row["query_count"], row["blocked_count"])
                for row in conn.execute("SELECT ip, query_count, blocked_count FROM clients")
            }
        assert domains == {"a.com": (2, 1), "b.com": (1, 0)}
        assert clients == {"10.0.0.1": (2, 1), "10.0.0.2": (1, 0)}

    def test_minute_rollup_is_maintained(self, db: Database, base_ts: int) -> None:
        minute = 60 * 1_000_000_000
        _store(
            db,
            [
                make_record(ts_ns=base_ts, domain="a.com"),
                make_record(ts_ns=base_ts + 1, domain="b.com", reason="FilteredBlackList"),
                make_record(ts_ns=base_ts + minute, domain="c.com"),
            ],
        )
        with db.read() as conn:
            rows = conn.execute("SELECT * FROM stats_minute ORDER BY bucket").fetchall()
        assert [(row["total"], row["blocked"]) for row in rows] == [(2, 1), (1, 0)]

    def test_first_and_last_seen_span_the_batch(self, db: Database, base_ts: int) -> None:
        _store(
            db,
            [
                make_record(ts_ns=base_ts + 500, domain="a.com"),
                make_record(ts_ns=base_ts + 100, domain="a.com"),
                make_record(ts_ns=base_ts + 900, domain="a.com"),
            ],
        )
        with db.read() as conn:
            row = conn.execute(
                "SELECT first_seen_ns, last_seen_ns FROM domains WHERE name = 'a.com'"
            ).fetchone()
        assert row["first_seen_ns"] == base_ts + 100
        assert row["last_seen_ns"] == base_ts + 900


class TestClientNames:
    def test_adguard_name_is_recorded_without_clobbering_the_alias(
        self, db: Database, base_ts: int
    ) -> None:
        _store(db, [make_record(ts_ns=base_ts, domain="a.com", client_ip="10.0.0.1",
                                client_name="Living room TV")])
        with db.write() as conn:
            conn.execute("UPDATE clients SET alias = 'Nappali TV' WHERE ip = '10.0.0.1'")
            apply_client_names(conn, {"10.0.0.1": "AdGuard TV"})
        with db.read() as conn:
            row = conn.execute("SELECT alias, adguard_name FROM clients").fetchone()
        assert row["alias"] == "Nappali TV"
        assert row["adguard_name"] == "AdGuard TV"


class _FakeAdGuardClient:
    """Stands in for AdGuardClient, serving a fixed newest-first log."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.calls: list[str | None] = []

    async def querylog(
        self, *, limit: int = 500, older_than: str | None = None, search: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(older_than)
        pool = self.items
        if older_than:
            pool = [item for item in pool if item["time"] < older_than]
        page = pool[:limit]
        return {"data": page, "oldest": page[-1]["time"] if page else ""}

    async def aclose(self) -> None:
        return None


def _api_item(index: int) -> dict[str, Any]:
    return {
        "time": f"2024-05-01T10:{59 - index // 60:02d}:{59 - index % 60:02d}.000000000Z",
        "question": {"name": f"d{index}.com", "type": "A", "class": "IN"},
        "client": "192.168.1.5",
        "status": "NOERROR",
        "reason": "NotFilteredNotFound",
    }


class TestApiProviderPaging:
    @pytest.mark.anyio
    async def test_forward_pass_stops_at_the_checkpoint(self) -> None:
        items = [_api_item(i) for i in range(50)]
        client = _FakeAdGuardClient(items)
        provider = AdGuardApiQueryLogProvider(client, page_size=50)  # type: ignore[arg-type]

        first = await provider.fetch({}, max_pages=5)
        assert len(first.records) == 50

        # Nothing new: the second poll must come back empty after one page.
        client.calls.clear()
        second = await provider.fetch(first.checkpoint, max_pages=5)
        assert second.records == []
        assert len(client.calls) == 1

    @pytest.mark.anyio
    async def test_new_records_only(self) -> None:
        client = _FakeAdGuardClient([_api_item(i) for i in range(10, 50)])
        provider = AdGuardApiQueryLogProvider(client, page_size=50)  # type: ignore[arg-type]
        first = await provider.fetch({}, max_pages=5)

        client.items = [_api_item(i) for i in range(50)]  # 10 newer entries appear
        second = await provider.fetch(first.checkpoint, max_pages=5)

        assert len(second.records) == 10
        assert all(record.ts_ns > 0 for record in second.records)
        assert len(first.records) == 40

    @pytest.mark.anyio
    async def test_backfill_resumes_across_polls(self) -> None:
        client = _FakeAdGuardClient([_api_item(i) for i in range(120)])
        provider = AdGuardApiQueryLogProvider(client, page_size=20)  # type: ignore[arg-type]

        seen: set[str] = set()
        checkpoint: dict[str, Any] = {}
        for _ in range(10):
            result = await provider.fetch(checkpoint, max_pages=2)
            checkpoint = result.checkpoint
            seen.update(record.domain for record in result.records)
            if not result.more_available and checkpoint.get("backfill_done"):
                break

        assert len(seen) == 120, "every historical record should eventually be imported"

    @pytest.mark.anyio
    async def test_retention_floor_stops_the_backfill(self) -> None:
        from app.common.timeutil import parse_timestamp

        items = [_api_item(i) for i in range(120)]
        client = _FakeAdGuardClient(items)
        provider = AdGuardApiQueryLogProvider(client, page_size=20)  # type: ignore[arg-type]
        floor = parse_timestamp(items[40]["time"])

        checkpoint: dict[str, Any] = {}
        collected: list[Any] = []
        for _ in range(10):
            result = await provider.fetch(checkpoint, max_pages=3, floor_ts_ns=floor)
            checkpoint = result.checkpoint
            collected.extend(result.records)
            if not result.more_available:
                break

        assert all(record.ts_ns >= floor for record in collected)


class TestFileProviderTailing:
    @pytest.mark.anyio
    async def test_tails_appended_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "querylog.json"
        path.write_text(querylog_line(domain="one.com") + "\n")
        provider = AdGuardFileQueryLogProvider(path)

        first = await provider.fetch({}, max_pages=4)
        assert [record.domain for record in first.records] == ["one.com"]

        second = await provider.fetch(first.checkpoint, max_pages=4)
        assert second.records == []

        with path.open("a") as handle:
            handle.write(querylog_line(domain="two.com") + "\n")
        third = await provider.fetch(second.checkpoint, max_pages=4)
        assert [record.domain for record in third.records] == ["two.com"]

    @pytest.mark.anyio
    async def test_restarts_after_rotation(self, tmp_path: Path) -> None:
        path = tmp_path / "querylog.json"
        path.write_text(querylog_line(domain="one.com") + "\n")
        provider = AdGuardFileQueryLogProvider(path)
        first = await provider.fetch({}, max_pages=4)

        path.unlink()
        path.write_text(querylog_line(domain="fresh.com") + "\n")
        second = await provider.fetch(first.checkpoint, max_pages=4)
        assert [record.domain for record in second.records] == ["fresh.com"]

    @pytest.mark.anyio
    async def test_ignores_a_partial_trailing_line(self, tmp_path: Path) -> None:
        path = tmp_path / "querylog.json"
        path.write_text(querylog_line(domain="one.com") + "\n" + '{"T":"2024')
        provider = AdGuardFileQueryLogProvider(path)

        first = await provider.fetch({}, max_pages=4)
        assert [record.domain for record in first.records] == ["one.com"]

        # Completing the line makes it readable on the next pass.
        with path.open("a") as handle:
            handle.write('-05-01T10:11:12Z","QH":"two.com","QT":"A","IP":"1.1.1.1","Result":{}}\n')
        second = await provider.fetch(first.checkpoint, max_pages=4)
        assert [record.domain for record in second.records] == ["two.com"]

    @pytest.mark.anyio
    async def test_missing_file_reports_unavailable(self, tmp_path: Path) -> None:
        provider = AdGuardFileQueryLogProvider(tmp_path / "nope.json")
        status = await provider.status()
        assert status.available is False
        assert "does not exist" in status.detail
        assert await provider.fetch({}, max_pages=1) is not None
