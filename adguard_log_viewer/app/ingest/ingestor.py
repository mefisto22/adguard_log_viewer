"""The ingest loop.

One task owns the whole pipeline: poll the provider, write the batch, refresh
the derived data, publish a notification, sleep. Everything it does is
incremental — a poll costs work proportional to the number of *new* records.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from contextlib import suppress
from typing import Any

from app.common.timeutil import now_ns
from app.db.sqlutil import kv_get, kv_set
from app.ingest.provider import Checkpoint
from app.runtime import AppState
from app.services.classification import classify_domains, get_ruleset_rev, stale_domains
from app.services.ingest_store import IngestStats, apply_client_names, store_records
from app.services.retention import cleanup, cutoff_for
from app.services.settings_service import effective_retention_days, ingest_enabled

_LOGGER = logging.getLogger(__name__)

CHECKPOINT_KEY = "checkpoint"

#: Domains re-classified per cycle when the rule set changed.
RECLASSIFY_BATCH = 500

#: How often the AdGuard client-name list is refreshed, in seconds.
CLIENT_NAME_INTERVAL = 300


class Ingestor:
    def __init__(self, state: AppState) -> None:
        self._state = state
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._stopping = asyncio.Event()
        self._last_client_names = 0.0
        self._last_cleanup = 0.0
        self._consecutive_errors = 0

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="ingest")

    async def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError, Exception):  # shutdown must not raise
                await self._task
            self._task = None

    def trigger(self) -> None:
        """Ask the loop to poll immediately instead of waiting out its sleep."""
        self._wake.set()

    # -- main loop ----------------------------------------------------------

    async def _run(self) -> None:
        settings = self._state.settings
        _LOGGER.info("Ingest loop started (every %ds)", settings.poll_interval)
        while not self._stopping.is_set():
            delay = float(settings.poll_interval)
            try:
                stats = await self.run_once()
                self._consecutive_errors = 0
                self._state.ingest_error = ""
                if stats.inserted and self._more_pending:
                    delay = 0.5  # keep draining a backlog without a full sleep
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self._consecutive_errors += 1
                self._state.ingest_error = str(err)
                delay = min(300.0, settings.poll_interval * min(self._consecutive_errors, 10))
                if self._consecutive_errors in (1, 5) or self._consecutive_errors % 20 == 0:
                    _LOGGER.error(
                        "Ingest failed (attempt %d, retrying in %.0fs): %s",
                        self._consecutive_errors,
                        delay,
                        err,
                    )

            with suppress(TimeoutError):  # the timeout is the normal path
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
            self._wake.clear()

    # -- one cycle ----------------------------------------------------------

    _more_pending = False

    async def run_once(self) -> IngestStats:
        state = self._state
        settings = state.settings
        provider = state.provider
        stats = IngestStats()
        if provider is None:
            return stats

        runtime = await state.db.run_read(
            lambda conn: (
                dict(kv_get(conn, "ingest_state", CHECKPOINT_KEY, {}) or {}),
                effective_retention_days(conn, settings),
                ingest_enabled(conn, settings),
            )
        )
        checkpoint, retention_days, enabled = runtime
        if not enabled:
            state.last_ingest = {"paused": True, "at_ns": now_ns()}
            return stats
        floor_ns = cutoff_for(retention_days)

        result = await provider.fetch(
            checkpoint, max_pages=settings.max_pages_per_poll, floor_ts_ns=floor_ns
        )
        self._more_pending = result.more_available

        if result.records:
            stats = await state.db.run_write(
                lambda conn: self._write_batch(conn, result.records, result.checkpoint)
            )
        else:
            await state.db.run_write(
                lambda conn: kv_set(conn, "ingest_state", CHECKPOINT_KEY, result.checkpoint)
            )

        state.last_ingest = {
            **stats.as_dict(),
            "at_ns": now_ns(),
            "provider": provider.name,
            "more_pending": result.more_available,
        }
        if stats.inserted:
            # Most polls import nothing, and overwriting this every time meant
            # the Settings page always read "0 new records" however healthy
            # ingest was. Keep the last poll that actually did something.
            state.last_import = dict(state.last_ingest)

        if stats.inserted:
            await state.events.publish(
                {
                    "type": "queries",
                    "inserted": stats.inserted,
                    "last_id": stats.last_id,
                    "new_domains": stats.new_domains,
                    "new_clients": stats.new_clients,
                    "at_ns": state.last_ingest["at_ns"],
                }
            )

        await self._refresh_client_names()
        await self._reclassify_stale()
        await self._maybe_cleanup()
        return stats

    def _write_batch(
        self, conn: sqlite3.Connection, records: list[Any], checkpoint: Checkpoint
    ) -> IngestStats:
        state = self._state
        revision = get_ruleset_rev(conn)
        stats = store_records(
            conn,
            records,
            engine=state.engine,
            revision=revision,
            resolver=state.new_tag_resolver(conn),
            tag_colors=state.tag_colors,
        )
        kv_set(conn, "ingest_state", CHECKPOINT_KEY, checkpoint)
        kv_set(conn, "ingest_state", "last_run_ns", now_ns())
        return stats

    # -- periodic side work -------------------------------------------------

    async def _refresh_client_names(self) -> None:
        provider = self._state.provider
        if provider is None:
            return
        if time.monotonic() - self._last_client_names < CLIENT_NAME_INTERVAL:
            return
        self._last_client_names = time.monotonic()
        try:
            names = await provider.client_names()
        except Exception as err:
            _LOGGER.debug("Could not refresh client names: %s", err)
            return
        if names:
            updated = await self._state.db.run_write(lambda conn: apply_client_names(conn, names))
            if updated:
                _LOGGER.info("Updated %d client name(s) from AdGuard", updated)

    async def _reclassify_stale(self) -> None:
        state = self._state
        if state.engine is None:
            return

        def _work(conn: sqlite3.Connection) -> int:
            revision = get_ruleset_rev(conn)
            pending = stale_domains(conn, revision=revision, limit=RECLASSIFY_BATCH)
            if not pending:
                return 0
            return classify_domains(
                conn,
                state.engine,  # type: ignore[arg-type]
                pending,
                revision=revision,
                resolver=state.new_tag_resolver(conn),
                tag_colors=state.tag_colors,
            )

        processed = await state.db.run_write(_work)
        if processed:
            _LOGGER.info("Re-classified %d domain(s) after a rule change", processed)

    async def _maybe_cleanup(self) -> None:
        settings = self._state.settings
        if time.monotonic() - self._last_cleanup < settings.cleanup_interval:
            return
        self._last_cleanup = time.monotonic()

        def _run(conn: sqlite3.Connection) -> Any:
            days = effective_retention_days(conn, settings)
            if days <= 0:
                return cleanup(conn, 0)
            return cleanup(conn, days)

        result = await self._state.db.run_write(_run)
        if result.deleted_queries:
            await self._state.events.publish(
                {"type": "cleanup", **result.as_dict(), "at_ns": now_ns()}
            )
