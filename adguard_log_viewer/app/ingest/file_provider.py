"""Query log provider that tails AdGuard's ``querylog.json`` directly.

**Not the default on Home Assistant OS.** A Home Assistant app cannot mount
another app's ``/data`` directory — see ARCHITECTURE.md §2 for the full
analysis. This provider exists for:

* Home Assistant Supervised / Container / plain Docker, where the file can be
  bind-mounted into this container;
* development and testing against a captured log file.

The file is JSON Lines in AdGuard's compact internal format, where the DNS
response is a base64-encoded wire message (decoded by :mod:`app.ingest.dns_wire`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import BinaryIO

import anyio

from app.common.domains import normalize_domain
from app.common.timeutil import parse_timestamp
from app.i18n import Message
from app.ingest.dns_wire import parse_base64_message
from app.ingest.provider import Checkpoint, FetchResult, ProviderStatus, QueryLogProvider
from app.ingest.records import QueryRecord, reason_name

_LOGGER = logging.getLogger(__name__)

KEY_FILE_KEY = "file_key"
KEY_OFFSET = "offset"
KEY_LAST_TS = "last_ts_ns"
KEY_HEAD = "head"
KEY_HEAD_LEN = "head_len"

#: Bytes read per page. One page is roughly 2000-4000 query log lines.
CHUNK_BYTES = 1 << 20

#: Largest prefix fingerprinted for rotation detection. A few hundred bytes is
#: several query log lines — more than enough to tell two files apart, and
#: cheap to re-read on every poll.
HEAD_BYTES = 4096


def _fingerprint(handle: BinaryIO, length: int) -> str:
    """Digest of the first *length* bytes. Restores the file position."""
    if length <= 0:
        return ""
    position = handle.tell()
    try:
        handle.seek(0)
        return hashlib.blake2b(handle.read(length), digest_size=16).hexdigest()
    finally:
        handle.seek(position)


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
                    detail=Message(
                        "{path} does not exist inside this container. On Home "
                        "Assistant OS an app cannot read another app's data "
                        "directory — use the AdGuard API provider instead.",
                        path=self.path,
                    ),
                )
            if not os.access(self.path, os.R_OK):
                return ProviderStatus(
                    name=self.name,
                    available=False,
                    source=str(self.path),
                    detail=Message(
                        "{path} exists but is not readable by this app.",
                        path=self.path,
                    ),
                )
            stat = self.path.stat()
            return ProviderStatus(
                name=self.name,
                available=True,
                source=str(self.path),
                detail=Message("Tailing {path}", path=self.path),
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

    def _rotation_reason(
        self, state: Checkpoint, handle: BinaryIO, size: int, key: str
    ) -> str | None:
        """Why the file must be re-read from the start, if it must.

        Three signals, because no single one is enough:

        * a different ``(device, inode)`` — the usual rotation;
        * a file shorter than the offset already consumed — truncation;
        * a changed fingerprint of the bytes already consumed — the file was
          replaced by one that happens to land on the same inode (Linux reuses
          a freshly freed inode readily) or was rewritten in place. Without
          this check the provider seeks past the new content and reports
          nothing, which is exactly what a same-size replacement looks like.
        """
        if not state:
            return None  # first run: there is nothing to compare against
        if state.get(KEY_FILE_KEY) != key:
            return "it was replaced"
        if int(state.get(KEY_OFFSET) or 0) > size:
            return "it was truncated"

        head_len = int(state.get(KEY_HEAD_LEN) or 0)
        stored = state.get(KEY_HEAD)
        if head_len and stored:
            if size < head_len:
                return "it got shorter"
            if _fingerprint(handle, head_len) != stored:
                return "its contents were rewritten"
        return None

    def _read_sync(
        self, state: Checkpoint, max_pages: int, floor_ts_ns: int | None
    ) -> FetchResult:
        try:
            handle = self.path.open("rb")
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            return FetchResult(records=[], checkpoint=state)

        records: list[QueryRecord] = []
        last_ts = int(state.get(KEY_LAST_TS) or 0)
        more = False
        remainder = b""

        with handle:
            stat = os.fstat(handle.fileno())
            key = _file_key(stat)
            offset = int(state.get(KEY_OFFSET) or 0)

            reason = self._rotation_reason(state, handle, stat.st_size, key)
            if reason is not None:
                _LOGGER.info(
                    "Query log %s: %s. Reading it from the beginning.", self.path, reason
                )
                offset = 0
            elif not state:
                offset = 0

            state[KEY_FILE_KEY] = key
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

            # Fingerprint what has been consumed, so a replacement file that
            # lands on the same inode with the same size is still detected.
            # The window only ever grows, which keeps the comparison stable
            # while the file is appended to.
            head_len = min(HEAD_BYTES, offset) if offset else 0
            state[KEY_HEAD_LEN] = head_len
            state[KEY_HEAD] = _fingerprint(handle, head_len) if head_len else ""

        state[KEY_OFFSET] = offset
        state[KEY_LAST_TS] = last_ts
        _LOGGER.debug("File fetch: %d records, offset now %d", len(records), offset)
        return FetchResult(records=records, checkpoint=state, more_available=more)
