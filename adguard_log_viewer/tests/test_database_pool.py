"""Read connections are pooled, not tied to threads.

The first version kept one read connection per thread, in thread-local
storage, and remembered every one of them so it could close them at shutdown.
anyio retires a worker thread after ten idle seconds, so under the ordinary
rhythm of this app — an ingest poll, a quiet spell, a dashboard load — new
threads kept arriving and each opened a connection that nothing ever closed.
Every connection holds two or three file descriptors. After a few hours the
process hit its limit, ``accept()`` began failing with EMFILE, and the web
interface lost its connection for good while the log filled with thousands of
identical tracebacks a second.

These tests pin the property that fixes it: the number of open connections is
bounded, whatever the threads do.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from app.db import database as database_module
from app.db.database import READER_POOL_SIZE, Database, QueryTimeout
from app.db.migrations import migrate


@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "pool.db")
    database.connect()
    migrate(database.write_connection)
    yield database
    database.close()


def open_descriptors() -> int | None:
    for path in ("/proc/self/fd", "/dev/fd"):
        if os.path.isdir(path):
            return len(os.listdir(path))
    return None  # pragma: no cover - no way to count on this platform


def read_once(db: Database) -> None:
    with db.read() as conn:
        conn.execute("SELECT count(*) FROM queries").fetchone()


class TestBoundedConnections:
    def test_short_lived_threads_do_not_open_new_connections(self, db: Database) -> None:
        """What anyio's pool looks like over time: threads come and go."""
        for _ in range(60):
            worker = threading.Thread(target=read_once, args=(db,))
            worker.start()
            worker.join()
        # One at a time, so one connection is enough — and it is reused.
        assert db.reader_count == 1

    def test_file_descriptors_stay_flat(self, db: Database) -> None:
        read_once(db)  # let the first connection open
        baseline = open_descriptors()
        if baseline is None:  # pragma: no cover
            pytest.skip("cannot count open file descriptors here")
        for _ in range(100):
            worker = threading.Thread(target=read_once, args=(db,))
            worker.start()
            worker.join()
        assert open_descriptors() == baseline

    def test_concurrency_never_exceeds_the_pool(self, db: Database) -> None:
        barrier = threading.Barrier(READER_POOL_SIZE * 2)
        errors: list[BaseException] = []

        def hold() -> None:
            try:
                barrier.wait(timeout=10)
                with db.read() as conn:
                    conn.execute("SELECT count(*) FROM queries").fetchone()
                    time.sleep(0.02)
            except BaseException as err:  # pragma: no cover - reported below
                errors.append(err)

        workers = [threading.Thread(target=hold) for _ in range(READER_POOL_SIZE * 2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=30)

        assert not errors
        assert all(not worker.is_alive() for worker in workers), "a reader deadlocked"
        assert db.reader_count <= READER_POOL_SIZE

    def test_a_nested_read_reuses_the_outer_connection(
        self, db: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With a pool of one, a nested read taking a second connection would hang."""
        monkeypatch.setattr(database_module, "READER_POOL_SIZE", 1)
        monkeypatch.setattr(database_module, "READER_WAIT_SECONDS", 1.0)
        with db.read() as outer, db.read() as inner:
            assert inner is outer
        assert db.reader_count == 1

    def test_a_connection_is_handed_back_after_an_error(self, db: Database) -> None:
        with pytest.raises(sqlite3.OperationalError), db.read() as conn:
            conn.execute("SELECT * FROM no_such_table")
        # Had it leaked, the next read would have to open a second connection.
        read_once(db)
        assert db.reader_count == 1


class TestDeadlinesStillWork:
    def test_a_slow_read_is_interrupted(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "slow.db", read_timeout=0.1)
        database.connect()
        try:
            with pytest.raises(QueryTimeout), database.read() as conn:
                conn.execute(
                    "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
                    "SELECT count(*) FROM n"
                ).fetchone()
        finally:
            database.close()

    def test_a_timed_out_connection_is_usable_afterwards(self, tmp_path: Path) -> None:
        """The deadline belongs to the query, not to the pooled connection."""
        database = Database(tmp_path / "slow.db", read_timeout=0.1)
        database.connect()
        try:
            with pytest.raises(QueryTimeout), database.read() as conn:
                conn.execute(
                    "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
                    "SELECT count(*) FROM n"
                ).fetchone()
            with database.read() as conn:
                assert conn.execute("SELECT 1").fetchone()[0] == 1
        finally:
            database.close()


class TestShutdown:
    def test_close_closes_every_pooled_connection(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "close.db")
        database.connect()
        migrate(database.write_connection)
        read_once(database)
        baseline = open_descriptors()
        database.close()
        if baseline is not None:
            assert open_descriptors() < baseline
        with pytest.raises(RuntimeError):
            read_once(database)


class TestDescriptorWatch:
    def test_usage_is_reported(self) -> None:
        from app.common.resources import descriptor_usage

        usage = descriptor_usage()
        if usage is None:  # pragma: no cover
            pytest.skip("cannot read the descriptor limit here")
        assert 0 < usage.open < usage.limit

    def test_warns_once_near_the_limit_and_again_after_recovering(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.common import resources

        readings = iter([90, 95, 10, 90])
        monkeypatch.setattr(
            resources,
            "descriptor_usage",
            lambda: resources.DescriptorUsage(open=next(readings), limit=100),
        )
        watch = resources.DescriptorWatch()
        with caplog.at_level("WARNING", logger="app.common.resources"):
            for _ in range(4):
                watch.check()
        warnings = [r for r in caplog.records if "file descriptors are open" in r.getMessage()]
        # 90 warns, 95 stays quiet, 10 re-arms, 90 warns again.
        assert len(warnings) == 2

    def test_the_status_endpoint_carries_it(self, bare_client) -> None:
        process = bare_client.get("/api/status").json()["process"]
        descriptors = process["descriptors"]
        if descriptors is None:  # pragma: no cover
            pytest.skip("cannot read the descriptor limit here")
        assert descriptors["open"] > 0 and descriptors["limit"] > descriptors["open"]
