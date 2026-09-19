"""The query log source abstraction.

The rest of the application depends on :class:`QueryLogProvider` only, never on
a concrete source. Swapping the AdGuard HTTP API for direct file access — or for
something else entirely later on — touches nothing outside this package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.i18n import localize, localize_all
from app.ingest.records import QueryRecord

#: Opaque, JSON-serialisable position in the source. Persisted in ``ingest_state``.
Checkpoint = dict[str, Any]


@dataclass(slots=True)
class ProviderStatus:
    """What the UI shows on the Settings page about the data source."""

    name: str
    available: bool
    source: str
    detail: str = ""
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "source": self.source,
            "detail": localize(self.detail),
            "warnings": localize_all(list(self.warnings)),
            "extra": dict(self.extra),
        }


@dataclass(slots=True)
class FetchResult:
    """One poll's worth of work."""

    records: list[QueryRecord]
    checkpoint: Checkpoint
    #: True when the provider stopped on its page budget and has more to give,
    #: so the ingest loop can poll again immediately instead of sleeping.
    more_available: bool = False


class QueryLogProvider(ABC):
    """Reads new query log records from somewhere."""

    name: ClassVar[str] = "provider"

    async def start(self) -> None:  # noqa: B027 - optional hook; not every provider needs it
        """Open whatever resources the provider needs."""

    async def close(self) -> None:  # noqa: B027 - optional hook; not every provider needs it
        """Release resources. Must be safe to call twice."""

    @abstractmethod
    async def status(self) -> ProviderStatus:
        """Probe the source and describe its health."""

    @abstractmethod
    async def fetch(
        self,
        checkpoint: Checkpoint,
        *,
        max_pages: int,
        floor_ts_ns: int | None = None,
    ) -> FetchResult:
        """Return records newer than *checkpoint*.

        ``floor_ts_ns`` is the retention horizon: the provider must not spend
        effort on history older than this.
        """

    async def client_names(self) -> dict[str, str]:
        """Optional ``{ip: name}`` mapping the source knows about."""
        return {}
