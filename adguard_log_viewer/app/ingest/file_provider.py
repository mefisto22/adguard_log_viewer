"""Query log provider that tails AdGuard's ``querylog.json`` directly.

**Not the default on Home Assistant OS.** A Home Assistant add-on cannot mount
another add-on's ``/data`` directory — see ARCHITECTURE.md §2 for the full
analysis. This provider exists for:

* Home Assistant Supervised / Container / plain Docker, where the file can be
  bind-mounted into this container;
* development and testing against a captured log file.

The file is JSON Lines in AdGuard's compact internal format, where the DNS
response is a base64-encoded wire message (decoded by :mod:`app.ingest.dns_wire`).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import anyio

from app.common.domains import normalize_domain
from app.common.timeutil import parse_timestamp
from app.ingest.dns_wire import parse_base64_message
from app.ingest.provider import Checkpoint, FetchResult, ProviderStatus, QueryLogProvider
from app.ingest.records import QueryRecord, reason_name

_LOGGER = logging.getLogger(__name__)

KEY_FILE_KEY = "file_key"
KEY_OFFSET = "offset"
KEY_LAST_TS = "last_ts_ns"

#: Bytes read per page. One page is roughly 2000-4000 query log lines.
CHUNK_BYTES = 1 << 20


def parse_file_record(line: str) -> QueryRecord | None:
    """Convert one ``querylog.json`` line into a :class:`QueryRecord`."""
    line = line.strip()
    if not line or not line.startswith("{"):
        return None
    try:
        item = json.loads(line)
    except ValueError:
        return None
    if not isinstance(item, dict):
        return None

    domain = normalize_domain(item.get("QH"))
    client_ip = str(item.get("IP") or item.get("Client") or "").strip()
    if not domain or not client_ip:
        return None

    try:
        ts_ns = parse_timestamp(str(item.get("T") or item.get("Time") or ""))
    except ValueError:
        return None

    result = item.get("Result")
    result = result if isinstance(result, dict) else {}

    rule_text = ""
    filter_list_id = -1
    rules = result.get("Rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            text = str(rule.get("Text") or "")
            if text and not rule_text:
                rule_text = text
            list_id = rule.get("FilterListID")
            if isinstance(list_id, int) and filter_list_id < 0:
                filter_list_id = list_id
    if not rule_text:
        rule_text = str(result.get("Rule") or "")
    if filter_list_id < 0 and isinstance(result.get("FilterID"), int):
        filter_list_id = int(result["FilterID"])

    status, answers = parse_base64_message(item.get("Answer"))
    if not answers and item.get("OrigAnswer"):
        _, answers = parse_base64_message(item.get("OrigAnswer"))

    elapsed_ns = item.get("Elapsed")
    elapsed_us = int(elapsed_ns) // 1000 if isinstance(elapsed_ns, (int, float)) else 0

    return QueryRecord(
        ts_ns=ts_ns,
        domain=domain,
        client_ip=client_ip,
        client_name="",
        qtype=str(item.get("QT") or "").upper(),
        qclass=str(item.get("QC") or "IN").upper(),
        status=status,
        reason=reason_name(result.get("Reason")),
        rule_text=rule_text,
        filter_list_id=filter_list_id,
        elapsed_us=max(0, elapsed_us),
        upstream=str(item.get("Upstream") or ""),
        cached=bool(item.get("Cached")),
        client_proto=str(item.get("CP") or ""),
        answers=list(answers),
    )


def _file_key(stat: os.stat_result) -> str:
    return f"{stat.st_dev}:{stat.st_ino}"


class AdGuardFileQueryLogProvider(QueryLogProvider):
    name = "adguard-file"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # -- status -------------------------------------------------------------

    async def status(self) -> ProviderStatus:
        def _probe() -> ProviderStatus:
            if not self.path.exists():
                return ProviderStatus(
                    name=self.name,
                    available=False,
                    source=str(self.path),
                    detail=(
                        f"{self.path} does not exist inside this container. On Home "
                        "Assistant OS an add-on cannot read another add-on's data "
                        "directory — use the AdGuard API provider instead."
                    ),
                )
            if not os.access(self.path, os.R_OK):
                return ProviderStatus(
                    name=self.name,
                    available=False,
                    source=str(self.path),
                    detail=f"{self.path} exists but is not readable by this add-on.",
                )
            stat = self.path.stat()
            return ProviderStatus(
                name=self.name,
                available=True,
                source=str(self.path),
                detail=f"Tailing {self.path}",
                extra={"size_bytes": stat.st_size},
            )

        return await anyio.to_thread.run_sync(_probe)

    # -- fetching -----------------------------------------------------------

    async def fetch(
        self,
        checkpoint: Checkpoint,
        *,
        max_pages: int,
        floor_ts_ns: int | None = None,
    ) -> FetchResult:
        def _read() -> FetchResult:
            return self._read_sync(dict(checkpoint), max_pages, floor_ts_ns)

        return await anyio.to_thread.run_sync(_read)

    def _read_sync(
        self, state: Checkpoint, max_pages: int, floor_ts_ns: int | None
    ) -> FetchResult:
        if not self.path.exists():
            return FetchResult(records=[], checkpoint=state)

        stat = self.path.stat()
        key = _file_key(stat)
        offset = int(state.get(KEY_OFFSET) or 0)

        if state.get(KEY_FILE_KEY) != key:
            # First run, or AdGuard rotated the log into querylog.json.1.
            if state.get(KEY_FILE_KEY):
                _LOGGER.info("Query log rotated, restarting from the beginning of %s", self.path)
            offset = 0
            state[KEY_FILE_KEY] = key
        elif offset > stat.st_size:
            _LOGGER.info("Query log truncated, restarting from the beginning of %s", self.path)
            offset = 0

        records: list[QueryRecord] = []
        last_ts = int(state.get(KEY_LAST_TS) or 0)
        more = False
        remainder = b""

        with self.path.open("rb") as handle:
            handle.seek(offset)
            for _ in range(max_pages):
                chunk = handle.read(CHUNK_BYTES)
                if not chunk:
                    break
                buffer = remainder + chunk
                lines = buffer.split(b"\n")
                remainder = lines.pop()  # trailing partial line
                for raw in lines:
                    offset += len(raw) + 1
                    record = parse_file_record(raw.decode("utf-8", "replace"))
                    if record is None or not record.is_valid():
                        continue
                    if floor_ts_ns is not None and record.ts_ns < floor_ts_ns:
                        continue
                    last_ts = max(last_ts, record.ts_ns)
                    records.append(record)
            else:
                more = bool(handle.read(1))

        state[KEY_OFFSET] = offset
        state[KEY_LAST_TS] = last_ts
        _LOGGER.debug("File fetch: %d records, offset now %d", len(records), offset)
        return FetchResult(records=records, checkpoint=state, more_available=more)
