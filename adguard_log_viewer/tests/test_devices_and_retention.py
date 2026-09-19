"""IP to device mapping, device to person mapping, and retention cleanup."""

from __future__ import annotations

from typing import Any

import pytest

from app.common.timeutil import NS_PER_SECOND, now_ns
from app.db.database import Database
from app.filters.nodes import parse_filter
from app.services import device_service
from app.services.classification import TagResolver
from app.services.ingest_store import store_records
from app.services.query_service import list_queries
from app.services.retention import cleanup, cutoff_for
from tests.conftest import make_record


@pytest.fixture
def seeded(db: Database, engine: Any, base_ts: int) -> Database:
    records = [
        make_record(ts_ns=base_ts + 1, domain="a.com", client_ip="192.168.1.15"),
        make_record(ts_ns=base_ts + 2, domain="b.com", client_ip="192.168.1.16"),
        make_record(ts_ns=base_ts + 3, domain="c.com", client_ip="192.168.1.17"),
        make_record(ts_ns=base_ts + 4, domain="d.com", client_ip="192.168.1.99"),
    ]
    with db.write() as conn:
        store_records(conn, records, engine=engine, revision=1, resolver=TagResolver())
    return db


class TestIpToDeviceMapping:
    def test_alias_overrides_the_adguard_name(self, db: Database, base_ts: int) -> None:
        with db.write() as conn:
            store_records(
                conn,
                [
                    make_record(
                        ts_ns=base_ts,
                        domain="a.com",
                        client_ip="192.168.1.15",
                        client_name="iPhone-von-Peter",
                    )
                ],
                resolver=TagResolver(),
            )
            client_id = conn.execute("SELECT id FROM clients").fetchone()["id"]
            device_service.update_device(conn, client_id, alias="Péter telefonja")

        with db.read() as conn:
            device = device_service.get_device(conn, client_id)
        assert device is not None
        assert device["adguard_name"] == "iPhone-von-Peter"
        assert device["alias"] == "Péter telefonja"
        assert device["name"] == "Péter telefonja"

    def test_name_falls_back_to_adguard_then_to_the_ip(
        self, seeded: Database
    ) -> None:
        with seeded.read() as conn:
            devices = device_service.list_devices(conn, sort="ip")["items"]
        by_ip = {device["ip"]: device for device in devices}
        assert by_ip["192.168.1.99"]["name"] == "192.168.1.99"

    def test_devices_can_be_searched(self, db: Database, base_ts: int) -> None:
        with db.write() as conn:
            store_records(
                conn,
                [make_record(ts_ns=base_ts, domain="a.com", client_ip="10.1.2.3",
                             client_name="Nappali TV")],
                resolver=TagResolver(),
            )
        with db.read() as conn:
            assert device_service.list_devices(conn, search="Nappali")["total"] == 1
            assert device_service.list_devices(conn, search="10.1.2")["total"] == 1
            assert device_service.list_devices(conn, search="nothing")["total"] == 0


class TestDeviceToPersonMapping:
    def test_several_devices_map_to_one_person(self, seeded: Database) -> None:
        with seeded.write() as conn:
            peter = device_service.create_person(conn, name="Péter")
            ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM clients WHERE ip IN "
                    "('192.168.1.15', '192.168.1.16', '192.168.1.17')"
                )
            ]
            assert device_service.assign_devices(conn, peter, ids) == 3

        with seeded.read() as conn:
            persons = device_service.list_persons(conn)
            page = list_queries(
                conn,
                filter_node=parse_filter(
                    {"field": "person", "operator": "equals", "value": "Péter"}
                ),
                limit=50,
            )
        assert persons[0]["device_count"] == 3
        assert persons[0]["query_count"] == 3
        assert {item["domain"] for item in page.items} == {"a.com", "b.com", "c.com"}

    def test_several_people_at_once(self, seeded: Database) -> None:
        with seeded.write() as conn:
            peter = device_service.create_person(conn, name="Péter")
            anna = device_service.create_person(conn, name="Anna")
            device_service.update_device(
                conn,
                conn.execute("SELECT id FROM clients WHERE ip='192.168.1.15'").fetchone()["id"],
                person_id=peter,
            )
            device_service.update_device(
                conn,
                conn.execute("SELECT id FROM clients WHERE ip='192.168.1.16'").fetchone()["id"],
                person_id=anna,
            )

        with seeded.read() as conn:
            page = list_queries(
                conn,
                filter_node=parse_filter(
                    {"field": "person", "operator": "in", "values": ["Péter", "Anna"]}
                ),
                limit=50,
            )
        assert {item["domain"] for item in page.items} == {"a.com", "b.com"}

    def test_deleting_a_person_keeps_their_devices(self, seeded: Database) -> None:
        with seeded.write() as conn:
            peter = device_service.create_person(conn, name="Péter")
            client_id = conn.execute(
                "SELECT id FROM clients WHERE ip='192.168.1.15'"
            ).fetchone()["id"]
            device_service.update_device(conn, client_id, person_id=peter)
            assert device_service.delete_person(conn, peter) is True

        with seeded.read() as conn:
            device = device_service.get_device(conn, client_id)
        assert device is not None
        assert device["person_id"] is None

    def test_a_person_needs_a_name(self, db: Database) -> None:
        with db.write() as conn, pytest.raises(ValueError):
            device_service.create_person(conn, name="   ")

    def test_clearing_the_person(self, seeded: Database) -> None:
        with seeded.write() as conn:
            person = device_service.create_person(conn, name="X")
            client_id = conn.execute("SELECT id FROM clients LIMIT 1").fetchone()["id"]
            device_service.update_device(conn, client_id, person_id=person)
            device_service.update_device(conn, client_id, clear_person=True)
            device = device_service.get_device(conn, client_id)
        assert device is not None
        assert device["person_id"] is None


class TestRetention:
    def test_cutoff(self) -> None:
        reference = 1_000_000 * NS_PER_SECOND
        assert cutoff_for(0) is None
        assert cutoff_for(-1) is None
        assert cutoff_for(1, reference_ns=reference) == reference - 86_400 * NS_PER_SECOND

    def test_old_queries_are_deleted(self, db: Database, engine: Any) -> None:
        now = now_ns()
        old = now - 40 * 86_400 * NS_PER_SECOND
        recent = now - 3600 * NS_PER_SECOND
        with db.write() as conn:
            store_records(
                conn,
                [
                    make_record(ts_ns=old, domain="old.com", client_ip="10.0.0.1"),
                    make_record(ts_ns=old + 1, domain="old.com", client_ip="10.0.0.1"),
                    make_record(ts_ns=recent, domain="new.com", client_ip="10.0.0.2"),
                ],
                engine=engine,
                revision=1,
                resolver=TagResolver(),
            )
            result = cleanup(conn, 30)

        assert result.deleted_queries == 2
        with db.read() as conn:
            remaining = [row["name"] for row in conn.execute("SELECT name FROM domains")]
            counts = conn.execute("SELECT COUNT(*) AS n FROM queries").fetchone()["n"]
            buckets = conn.execute("SELECT COUNT(*) AS n FROM stats_minute").fetchone()["n"]
        assert counts == 1
        assert remaining == ["new.com"]
        assert buckets == 1

    def test_unlimited_retention_deletes_nothing(self, db: Database, base_ts: int) -> None:
        with db.write() as conn:
            store_records(
                conn,
                [make_record(ts_ns=base_ts - 10**18, domain="ancient.com")],
                resolver=TagResolver(),
            )
            result = cleanup(conn, 0)
        assert result.deleted_queries == 0
        with db.read() as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM queries").fetchone()["n"] == 1

    def test_counters_are_recomputed_after_cleanup(self, db: Database) -> None:
        now = now_ns()
        old = now - 40 * 86_400 * NS_PER_SECOND
        with db.write() as conn:
            store_records(
                conn,
                [
                    make_record(ts_ns=old, domain="mixed.com", client_ip="10.0.0.1"),
                    make_record(ts_ns=now - 60 * NS_PER_SECOND, domain="mixed.com",
                                client_ip="10.0.0.1", reason="FilteredBlackList"),
                ],
                resolver=TagResolver(),
            )
            cleanup(conn, 30)
        with db.read() as conn:
            row = conn.execute(
                "SELECT query_count, blocked_count FROM domains WHERE name = 'mixed.com'"
            ).fetchone()
        assert (row["query_count"], row["blocked_count"]) == (1, 1)

    def test_named_devices_survive_cleanup(self, db: Database) -> None:
        now = now_ns()
        old = now - 40 * 86_400 * NS_PER_SECOND
        with db.write() as conn:
            store_records(
                conn,
                [
                    make_record(ts_ns=old, domain="a.com", client_ip="10.0.0.1"),
                    make_record(ts_ns=old, domain="b.com", client_ip="10.0.0.2"),
                ],
                resolver=TagResolver(),
            )
            named = conn.execute("SELECT id FROM clients WHERE ip='10.0.0.1'").fetchone()["id"]
            device_service.update_device(conn, named, alias="Fontos eszköz")
            cleanup(conn, 30)

        with db.read() as conn:
            remaining = [row["ip"] for row in conn.execute("SELECT ip FROM clients")]
        assert remaining == ["10.0.0.1"]
