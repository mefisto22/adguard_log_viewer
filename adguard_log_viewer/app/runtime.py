"""Process-wide state shared by the HTTP layer and the ingest loop."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

from app.adguard.client import AdGuardClient
from app.adguard.discovery import DiscoveredAdGuard, discover_adguard
from app.categorization.engine import CategorizationEngine
from app.config import Settings
from app.db.database import Database
from app.db.migrations import migrate
from app.db.sqlutil import kv_get, kv_set
from app.ingest.api_provider import AdGuardApiQueryLogProvider
from app.ingest.file_provider import AdGuardFileQueryLogProvider
from app.ingest.provider import ProviderStatus, QueryLogProvider
from app.services.classification import TagResolver, get_ruleset_rev
from app.services.events import EventBus
from app.services.rules_service import (
    build_engine,
    builtin_tag_colors,
    seed_builtin_tags,
)

_LOGGER = logging.getLogger(__name__)

#: How long a provider health probe stays fresh. Probing AdGuard costs two HTTP
#: round trips, and when it is unreachable each one waits out a connect
#: timeout — far too slow to do on every page load of the Settings screen.
PROVIDER_STATUS_TTL = 30.0


@dataclass
class AppState:
    """Everything the application needs at runtime, created once at startup."""

    settings: Settings
    db: Database
    events: EventBus = field(default_factory=EventBus)
    engine: CategorizationEngine | None = None
    provider: QueryLogProvider | None = None
    discovery: DiscoveredAdGuard | None = None
    #: Set by main.py once the ingest loop exists. Typed loosely to keep
    #: app.ingest.ingestor free to import this module.
    ingestor: Any = None
    tag_colors: dict[str, str] = field(default_factory=dict)
    ruleset_rev: int = 0
    last_ingest: dict[str, Any] = field(default_factory=dict)
    ingest_error: str = ""
    started_at_ns: int = 0
    _provider_status: tuple[float, ProviderStatus] | None = None
    #: Kept so the warm-up task is not garbage collected mid-flight.
    _warmup_task: asyncio.Task[None] | None = None

    # -- database -----------------------------------------------------------

    def init_database(self) -> None:
        self.db.connect()
        conn = self.db.write_connection
        migrate(conn)
        with self.db.write() as write_conn:
            seed_builtin_tags(write_conn)
            self.tag_colors = builtin_tag_colors()
            if kv_get(write_conn, "settings", "ruleset_rev") is None:
                kv_set(write_conn, "settings", "ruleset_rev", 1)
        self.reload_engine()

    def reload_engine(self) -> None:
        """Rebuild the categorisation engine from the current rule set."""
        with self.db.read() as conn:
            self.engine = build_engine(conn)
            self.ruleset_rev = get_ruleset_rev(conn)
        _LOGGER.info(
            "Categorisation engine loaded with %d rules (revision %d)",
            self.engine.rule_count if self.engine else 0,
            self.ruleset_rev,
        )

    def new_tag_resolver(self, conn: sqlite3.Connection) -> TagResolver:
        resolver = TagResolver()
        resolver.prime(conn)
        return resolver

    # -- provider -----------------------------------------------------------

    async def init_provider(self) -> None:
        """Pick and build the query log provider for this environment."""
        settings = self.settings
        choice = settings.provider

        if choice == "file" or (choice == "auto" and settings.querylog_path):
            if settings.querylog_path:
                self.provider = AdGuardFileQueryLogProvider(settings.querylog_path)
                _LOGGER.info("Using the file query log provider (%s)", settings.querylog_path)
                return
            _LOGGER.warning(
                "The file provider was requested but no query log path was configured; "
                "falling back to the AdGuard API."
            )

        self.discovery = await discover_adguard(
            supervisor_token=settings.supervisor_token,
            configured_url=settings.adguard_url,
            configured_slug=settings.adguard_slug,
        )
        for warning in self.discovery.warnings:
            _LOGGER.warning("%s", warning)

        client = AdGuardClient(
            self.discovery.url,
            username=settings.adguard_username,
            password=settings.adguard_password,
            verify_ssl=settings.adguard_verify_ssl,
        )
        self.provider = AdGuardApiQueryLogProvider(client, page_size=settings.ingest_batch_size)
        _LOGGER.info("Using the AdGuard API query log provider (%s)", self.discovery.url)

    async def provider_status(self, *, force: bool = False) -> ProviderStatus | None:
        """Health of the query log source, cached for :data:`PROVIDER_STATUS_TTL`."""
        if self.provider is None:
            return None
        now = time.monotonic()
        cached = self._provider_status
        if not force and cached is not None and now - cached[0] < PROVIDER_STATUS_TTL:
            return cached[1]
        status = await self.provider.status()
        self._provider_status = (now, status)
        return status

    def prime_provider_status(self) -> None:
        """Warm the cache in the background so the first page load is not slow."""

        async def _warm() -> None:
            try:
                await self.provider_status(force=True)
            except Exception as err:
                _LOGGER.debug("Could not prime the provider status: %s", err)

        self._warmup_task = asyncio.create_task(_warm(), name="provider-warmup")

    async def rebuild_provider(self) -> None:
        """Re-run discovery, for example after the user changed the settings."""
        if self.provider is not None:
            await self.provider.close()
            self.provider = None
        self._provider_status = None
        await self.init_provider()

    async def shutdown(self) -> None:
        if self._warmup_task is not None:
            self._warmup_task.cancel()
            self._warmup_task = None
        if self.provider is not None:
            await self.provider.close()
            self.provider = None
        self.db.close()
