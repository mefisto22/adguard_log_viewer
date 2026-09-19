"""Shared fixtures."""

from __future__ import annotations

import base64
import json
import struct
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.categorization.engine import CategorizationEngine
from app.common.timeutil import now_ns
from app.db.database import Database
from app.db.migrations import migrate
from app.db.sqlutil import kv_set
from app.ingest.records import DnsAnswer, QueryRecord
from app.services.rules_service import (
    build_engine,
    builtin_tag_colors,
    seed_builtin_tags,
)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "test.db")
    database.connect()
    migrate(database.write_connection)
    with database.write() as conn:
        seed_builtin_tags(conn)
        kv_set(conn, "settings", "ruleset_rev", 1)
    yield database
    database.close()


@pytest.fixture
def engine(db: Database) -> CategorizationEngine:
    with db.read() as conn:
        return build_engine(conn)


@pytest.fixture
def tag_colors() -> dict[str, str]:
    return builtin_tag_colors()


@pytest.fixture
def base_ts() -> int:
    return now_ns() - 3600 * 1_000_000_000


def make_record(
    *,
    ts_ns: int,
    domain: str,
    client_ip: str = "192.168.1.10",
    qtype: str = "A",
    reason: str = "",
    client_name: str = "",
    elapsed_us: int = 1000,
    upstream: str = "https://dns.quad9.net",
    status: str = "NOERROR",
) -> QueryRecord:
    return QueryRecord(
        ts_ns=ts_ns,
        domain=domain,
        client_ip=client_ip,
        client_name=client_name,
        qtype=qtype,
        status=status,
        reason=reason,
        elapsed_us=elapsed_us,
        upstream=upstream,
        answers=[DnsAnswer(type=qtype, value="1.2.3.4", ttl=300)],
    )


def dns_response(rcode: int = 0, *, answer_ip: str = "93.184.216.34") -> bytes:
    """Build a minimal DNS response message for the file-format tests."""
    message = struct.pack("!HHHHHH", 0x1234, 0x8180 | rcode, 1, 1, 0, 0)
    message += b"\x07example\x03com\x00" + struct.pack("!HH", 1, 1)
    octets = bytes(int(part) for part in answer_ip.split("."))
    message += b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + octets
    return message


def querylog_line(
    *,
    time: str = "2024-05-01T10:11:12.123456789Z",
    domain: str = "example.com",
    client: str = "192.168.1.5",
    qtype: str = "A",
    reason: int = 0,
    rules: list[dict] | None = None,
    elapsed_ns: int = 12_345_678,
    rcode: int = 0,
) -> str:
    payload = {
        "T": time,
        "QH": domain,
        "QT": qtype,
        "QC": "IN",
        "CP": "",
        "Upstream": "https://dns.quad9.net:443/dns-query",
        "Answer": base64.b64encode(dns_response(rcode)).decode(),
        "Result": {"Reason": reason, "Rules": rules or []},
        "Elapsed": elapsed_ns,
        "IP": client,
        "Cached": False,
    }
    return json.dumps(payload)


@pytest.fixture
def anyio_backend() -> str:
    """Run the async tests on asyncio only."""
    return "asyncio"


@pytest.fixture
def bare_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A running application with an empty database and no AdGuard reachable."""
    from fastapi.testclient import TestClient

    from app.config import reset_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INGEST_ENABLED", "false")
    monkeypatch.setenv("PROVIDER", "file")
    monkeypatch.setenv("QUERYLOG_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setenv("LOG_LEVEL", "error")
    monkeypatch.setenv("OPTIONS_FILE", str(tmp_path / "no-options.json"))
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    reset_settings()

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client
    reset_settings()
