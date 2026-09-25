"""SQLite access layer.

Design notes
------------
* The database runs in **WAL** mode, so a long-running read (a dashboard
  aggregation) never blocks the ingest writer and vice versa.
* Exactly one *write* connection exists, guarded by a lock. SQLite allows a
  single writer anyway, and serialising it here gives clean transactions.
* *Read* connections come from a **fixed-size pool**, not one per thread.
  The handlers run their database work on anyio's worker threads, and anyio
  retires a worker that has been idle for ten seconds. Tying a connection to
  a thread therefore opened a new connection for every new worker — and kept
  the old ones, which nothing ever closed. Each costs two or three file
  descriptors (the database, its ``-wal``, its ``-shm``), so a few hours of
  "poll, go quiet, poll" exhausted the process limit and the server stopped
  accepting connections altogether. A pool makes the count a constant.
* ``sqlite3`` has no ``REGEXP`` implementation; one is registered per connection
  so the filter engine can offer a ``regex`` operator.
"""

from __future__ import annotations

import logging
import queue
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, TypeVar

import anyio

from app.i18n import Message

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

#: A read may not run longer than this. A user-supplied regular expression is
#: evaluated per row and Python's `re` has no timeout of its own, so without a
#: ceiling one pathological pattern could pin a worker thread for minutes.
DEFAULT_READ_TIMEOUT = 30.0

#: How often SQLite calls the progress handler, in virtual machine steps.
PROGRESS_STEPS = 20_000

#: Read connections kept open. The dashboard issues its ten parts at once and
#: the ingest loop reads alongside it, so twelve lets that run in parallel; a
#: read beyond it waits for a connection rather than opening another.
READER_POOL_SIZE = 12

#: How long a read waits for a free connection before giving up. Reaching it
#: means every connection is held by a query that is itself past its own
#: deadline, which :data:`DEFAULT_READ_TIMEOUT` already bounds.
READER_WAIT_SECONDS = DEFAULT_READ_TIMEOUT * 2


class _Reader:
    """A pooled read connection and the deadline of the query it is running.

    The deadline lives here, not in thread-local state: a pooled connection
    serves many threads over its life, and the progress handler has to judge
    the query that is running on it *now*.
    """

    __slots__ = ("conn", "deadline")

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.deadline = 0.0


class QueryTimeout(RuntimeError):
    """A read was aborted because it exceeded the deadline."""

_REGEX_CACHE: dict[str, re.Pattern[str]] = {}
_REGEX_CACHE_LOCK = threading.Lock()
_REGEX_CACHE_LIMIT = 256


def _regexp(pattern: str | None, value: str | None) -> bool:
    """``REGEXP`` implementation for SQLite.

    Invalid patterns match nothing rather than raising, so a typo in a user
    supplied filter degrades to "no results" instead of a 500.
    """
    if pattern is None or value is None:
        return False
    with _REGEX_CACHE_LOCK:
        compiled = _REGEX_CACHE.get(pattern)
        if compiled is None:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error:
                return False
            if len(_REGEX_CACHE) >= _REGEX_CACHE_LIMIT:
                _REGEX_CACHE.clear()
            _REGEX_CACHE[pattern] = compiled
    return compiled.search(value) is not None


def _configure(conn: sqlite3.Connection, *, read_only: bool) -> None:
    conn.row_factory = sqlite3.Row
    conn.create_function("REGEXP", 2, _regexp, deterministic=True)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    if read_only:
        # Readers only need a small private cache; the shared WAL does the work.
        conn.execute("PRAGMA cache_size = -8000")
        conn.execute("PRAGMA query_only = ON")
    else:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -32000")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA wal_autocheckpoint = 2000")


class Database:
    """Owns the SQLite connections for one database file."""

    def __init__(self, path: Path | str, *, read_timeout: float = DEFAULT_READ_TIMEOUT) -> None:
        self.path = Path(path)
        self.read_timeout = read_timeout
        self._write_conn: sqlite3.Connection | None = None
        self._write_lock = threading.RLock()
        # Which pooled reader, if any, this thread is inside — so a read nested
        # in another read reuses the connection instead of taking a second one
        # (which, with every connection taken, would wait on itself forever).
        self._local = threading.local()
        self._pool: queue.LifoQueue[_Reader] = queue.LifoQueue()
        self._readers: list[_Reader] = []
        self._readers_lock = threading.Lock()
        self._closed = False

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> None:
        """Open the write connection, creating the file if needed."""
        if self._write_conn is not None:
            return
        if self.path.parent and str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,  # explicit transaction control
            timeout=30.0,
        )
        _configure(conn, read_only=False)
        self._write_conn = conn
        _LOGGER.info("Opened database at %s", self.path)

    def close(self) -> None:
        self._closed = True
        with self._readers_lock:
            for reader in self._readers:
                with suppress(sqlite3.Error):  # best effort during shutdown
                    reader.conn.close()
            self._readers.clear()
        self._pool = queue.LifoQueue()
        self._local = threading.local()
        with self._write_lock:
            if self._write_conn is not None:
                with suppress(sqlite3.Error):  # best effort during shutdown
                    self._write_conn.execute("PRAGMA optimize")
                self._write_conn.close()
                self._write_conn = None

    # -- connections --------------------------------------------------------

    @property
    def write_connection(self) -> sqlite3.Connection:
        if self._write_conn is None:
            raise RuntimeError("Database.connect() has not been called")
        return self._write_conn

    @property
    def reader_count(self) -> int:
        """Read connections currently open. Constant once the pool has filled."""
        with self._readers_lock:
            return len(self._readers)

    def _open_reader(self) -> _Reader:
        conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30.0)
        _configure(conn, read_only=True)
        reader = _Reader(conn)

        def _handler() -> int:
            deadline = reader.deadline
            return 1 if deadline and time.monotonic() > deadline else 0

        # Returning non-zero makes SQLite raise ``OperationalError: interrupted``.
        conn.set_progress_handler(_handler, PROGRESS_STEPS)
        return reader

    def _acquire(self) -> _Reader:
        if self._closed:
            raise RuntimeError("Database is closed")
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            pass
        with self._readers_lock:
            if len(self._readers) < READER_POOL_SIZE:
                reader = self._open_reader()
                self._readers.append(reader)
                return reader
        try:
            return self._pool.get(timeout=READER_WAIT_SECONDS)
        except queue.Empty:
            raise RuntimeError(
                "No database connection became free; every one is held by a running query"
            ) from None

    def _release(self, reader: _Reader) -> None:
        reader.deadline = 0.0
        if self._closed:
            with suppress(sqlite3.Error):
                reader.conn.close()
            return
        if reader.conn.in_transaction:
            # Reads do not open transactions, but a connection handed on must
            # never carry one — the next reader would see a stale snapshot.
            with suppress(sqlite3.Error):
                reader.conn.rollback()
        self._pool.put(reader)

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Yield a read-only connection, bounded by :attr:`read_timeout`."""
        if str(self.path) == ":memory:":
            # An in-memory database cannot be reopened; share the writer.
            yield self.write_connection
            return

        outer: _Reader | None = getattr(self._local, "reader", None)
        reader = outer if outer is not None else self._acquire()
        previous = reader.deadline
        reader.deadline = time.monotonic() + self.read_timeout
        self._local.reader = reader
        try:
            yield reader.conn
        except sqlite3.OperationalError as err:
            if "interrupted" in str(err).lower():
                raise QueryTimeout(
                    Message(
                        "The query was still running after {seconds} seconds and was "
                        "stopped. Narrow the time range, or simplify the filter — a regular "
                        "expression in particular cannot use an index.",
                        seconds=f"{self.read_timeout:.0f}",
                    )
                ) from err
            raise
        finally:
            reader.deadline = previous
            if outer is None:
                self._local.reader = None
                self._release(reader)

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """Yield the write connection inside a transaction.

        Commits on success, rolls back on any exception. Re-entrant: a nested
        ``write()`` joins the outer transaction.
        """
        with self._write_lock:
            conn = self.write_connection
            if conn.in_transaction:
                yield conn  # already inside an outer transaction
                return
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    # -- async helpers ------------------------------------------------------

    async def run_read(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        def _call() -> T:
            with self.read() as conn:
                return fn(conn)

        return await anyio.to_thread.run_sync(_call)

    async def run_write(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        def _call() -> T:
            with self.write() as conn:
                return fn(conn)

        return await anyio.to_thread.run_sync(_call)

    # -- maintenance --------------------------------------------------------

    def vacuum(self) -> None:
        with self._write_lock:
            self.write_connection.execute("VACUUM")

    def stats(self) -> dict[str, Any]:
        with self.read() as conn:
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        return {
            "path": str(self.path),
            "size_bytes": int(page_count) * int(page_size),
        }


_database: Database | None = None


def set_database(db: Database | None) -> None:
    global _database
    _database = db


def get_database() -> Database:
    if _database is None:
        raise RuntimeError("Database has not been initialised")
    return _database
