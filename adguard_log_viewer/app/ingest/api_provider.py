"""Query log provider backed by the AdGuard Home HTTP API.

This is the default on Home Assistant OS, where an app cannot read another
app's ``/data`` directory (ARCHITECTURE.md §2).

Paging strategy
---------------
AdGuard's ``/control/querylog`` only pages backwards, via ``older_than``. Each
poll therefore does two things:

* a **forward pass** from the newest record backwards, stopping as soon as it
  reaches a timestamp already ingested — so its cost is proportional to the
  delta, not to the size of the log;
* a **backfill pass** that keeps walking into history from where the previous
  poll's budget ran out, until the whole retention window has been imported.
"""

from __future__ import annotations

import logging
from typing import Any

from app.adguard.client import AdGuardClient, AdGuardError
from app.common.domains import normalize_domain
from app.common.timeutil import parse_timestamp
from app.i18n import Message, detail_of
from app.ingest.provider import Checkpoint, FetchResult, ProviderStatus, QueryLogProvider
from app.ingest.records import DnsAnswer, QueryRecord, reason_name

_LOGGER = logging.getLogger(__name__)

KEY_FORWARD_TS = "forward_ts_ns"
KEY_BACKFILL_CURSOR = "backfill_cursor"
KEY_BACKFILL_DONE = "backfill_done"


def parse_api_record(item: dict[str, Any]) -> QueryRecord | None:
    """Convert one ``QueryLogItem`` into a :class:`QueryRecord`."""
    if not isinstance(item, dict):
        return None

    question = item.get("question")
    if not isinstance(question, dict):
        return None

    domain = normalize_domain(question.get("name"))
    client_ip = str(item.get("client") or "").strip()
    if not domain or not client_ip:
        return None

    try:
        ts_ns = parse_timestamp(str(item.get("time") or ""))
    except ValueError:
        return None

    rules = item.get("rules")
    rule_text = ""
    filter_list_id = -1
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            text = str(rule.get("text") or "")
            if text and not rule_text:
                rule_text = text
            list_id = rule.get("filter_list_id")
            if isinstance(list_id, int) and filter_list_id < 0:
                filter_list_id = list_id
    if not rule_text:
        rule_text = str(item.get("rule") or "")
    if filter_list_id < 0 and isinstance(item.get("filterId"), int):
        filter_list_id = int(item["filterId"])

    answers: list[DnsAnswer] = []
    for entry in item.get("answer") or []:
        if not isinstance(entry, dict):
            continue
        answers.append(
            DnsAnswer(
                type=str(entry.get("type") or ""),
                value=str(entry.get("value") or ""),
                ttl=int(entry.get("ttl") or 0),
            )
        )

    client_info = item.get("client_info")
    client_name = ""
    if isinstance(client_info, dict):
        client_name = str(client_info.get("name") or "").strip()

    return QueryRecord(
        ts_ns=ts_ns,
        domain=domain,
        client_ip=client_ip,
        client_name=client_name,
        qtype=str(question.get("type") or "").upper(),
        qclass=str(question.get("class") or "IN").upper(),
        status=str(item.get("status") or ""),
        reason=reason_name(item.get("reason")),
        rule_text=rule_text,
        filter_list_id=filter_list_id,
        elapsed_us=_elapsed_us(item.get("elapsedMs")),
        upstream=str(item.get("upstream") or ""),
        cached=bool(item.get("cached")),
        client_proto=str(item.get("client_proto") or ""),
        answers=answers,
    )


def _elapsed_us(value: Any) -> int:
    try:
        return max(0, round(float(value) * 1000))
    except (TypeError, ValueError):
        return 0


class AdGuardApiQueryLogProvider(QueryLogProvider):
    name = "adguard-api"

    def __init__(
        self,
        client: AdGuardClient | None,
        *,
        page_size: int = 500,
        setup_error: str = "",
    ) -> None:
        """``client`` is ``None`` when AdGuard's address could not be worked out.

        The provider still exists in that state so the Settings page has
        something to report; ``setup_error`` is what it says, instead of a
        connection failure against an address nobody configured.
        """
        self._client = client
        self._page_size = max(50, page_size)
        self._setup_error = setup_error

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    # -- status -------------------------------------------------------------

    async def status(self) -> ProviderStatus:
        warnings: list[str] = []
        extra: dict[str, Any] = {}

        if self._client is None:
            return ProviderStatus(
                name=self.name,
                available=False,
                source="(address not determined)",
                detail=self._setup_error
                or Message("The AdGuard Home address could not be worked out."),
            )

        try:
            status = await self._client.status()
        except AdGuardError as err:
            hint = ""
            if err.is_auth_error:
                hint = Message(
                    " The AdGuard Home app protects its web port with Home Assistant "
                    "login by default — set a Home Assistant username and password in "
                    "this app's options."
                )
            return ProviderStatus(
                name=self.name,
                available=False,
                source=self._client.base_url,
                detail=Message("{error}{hint}", error=detail_of(err), hint=hint),
            )

        extra["adguard_version"] = str(status.get("version") or "")
        extra["protection_enabled"] = bool(status.get("protection_enabled"))
        if not status.get("running", True):
            warnings.append(Message("AdGuard Home reports that its DNS server is not running."))

        try:
            config = await self._client.querylog_config()
        except AdGuardError:
            config = {}
        if config and config.get("enabled") is False:
            warnings.append(
                Message("The query log is disabled in AdGuard Home; no new records will arrive.")
            )
        if config.get("anonymize_client_ip"):
            warnings.append(
                Message(
                    "AdGuard Home anonymises client IP addresses, so per-device "
                    "attribution will be incomplete."
                )
            )

        return ProviderStatus(
            name=self.name,
            available=True,
            source=self._client.base_url,
            detail=(
                Message("Connected to AdGuard Home {version}", version=extra["adguard_version"])
                if extra["adguard_version"]
                else Message("Connected to AdGuard Home")
            ),
            warnings=warnings,
            extra=extra,
        )

    async def client_names(self) -> dict[str, str]:
        if self._client is None:
            return {}
        return await self._client.client_names()

    # -- fetching -----------------------------------------------------------

    async def fetch(
        self,
        checkpoint: Checkpoint,
        *,
        max_pages: int,
        floor_ts_ns: int | None = None,
    ) -> FetchResult:
        if self._client is None:
            return FetchResult(records=[], checkpoint=dict(checkpoint))

        state: Checkpoint = dict(checkpoint)
        forward_ts: int = int(state.get(KEY_FORWARD_TS) or 0)
        records: list[QueryRecord] = []
        pages_used = 0
        more = False

        # --- forward pass: newest first, stop at the known horizon ---------
        older_than: str | None = None
        newest_ts = forward_ts
        caught_up = False

        while pages_used < max_pages:
            page = await self._client.querylog(limit=self._page_size, older_than=older_than)
            pages_used += 1
            items = page.get("data") or []
            if not items:
                caught_up = True
                break

            for item in items:
                record = parse_api_record(item)
                if record is None or not record.is_valid():
                    continue
                if record.ts_ns <= forward_ts:
                    caught_up = True
                    continue
                if floor_ts_ns is not None and record.ts_ns < floor_ts_ns:
                    # Outside the retention window; importing it would only give
                    # the cleanup job something to delete.
                    continue
                newest_ts = max(newest_ts, record.ts_ns)
                records.append(record)

            if caught_up:
                break
            oldest = str(page.get("oldest") or "")
            if not oldest:
                caught_up = True
                break
            if floor_ts_ns is not None and _safe_ts(oldest) < floor_ts_ns:
                caught_up = True
                break
            older_than = oldest

        if not caught_up and older_than:
            # Ran out of budget while still in unseen territory: remember where
            # to resume so history is not lost.
            state[KEY_BACKFILL_CURSOR] = older_than
            state[KEY_BACKFILL_DONE] = False
            more = True

        state[KEY_FORWARD_TS] = newest_ts

        # --- backfill pass: keep walking into history with the leftover budget
        cursor = state.get(KEY_BACKFILL_CURSOR)
        if not state.get(KEY_BACKFILL_DONE) and cursor and pages_used < max_pages:
            while pages_used < max_pages:
                page = await self._client.querylog(limit=self._page_size, older_than=cursor)
                pages_used += 1
                items = page.get("data") or []
                if not items:
                    state[KEY_BACKFILL_DONE] = True
                    state[KEY_BACKFILL_CURSOR] = None
                    break

                for item in items:
                    record = parse_api_record(item)
                    if record is None or not record.is_valid():
                        continue
                    if floor_ts_ns is not None and record.ts_ns < floor_ts_ns:
                        continue
                    records.append(record)

                oldest = str(page.get("oldest") or "")
                if not oldest or oldest == cursor:
                    state[KEY_BACKFILL_DONE] = True
                    state[KEY_BACKFILL_CURSOR] = None
                    break
                cursor = oldest
                state[KEY_BACKFILL_CURSOR] = cursor
                if floor_ts_ns is not None and _safe_ts(oldest) < floor_ts_ns:
                    state[KEY_BACKFILL_DONE] = True
                    state[KEY_BACKFILL_CURSOR] = None
                    break
            else:
                more = True

        _LOGGER.debug(
            "API fetch: %d records over %d page(s), backfill_done=%s",
            len(records),
            pages_used,
            state.get(KEY_BACKFILL_DONE),
        )
        return FetchResult(records=records, checkpoint=state, more_available=more)


def _safe_ts(value: str) -> int:
    try:
        return parse_timestamp(value)
    except ValueError:
        return 0
