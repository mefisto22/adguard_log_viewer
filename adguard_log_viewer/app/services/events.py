"""In-process pub/sub used by the Server-Sent Events endpoint.

The stream only carries *notifications* — "there are N new records, the highest
id is X". Clients then fetch the delta through the normal, filtered query API,
so the full query log is never pushed to the browser.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

_LOGGER = logging.getLogger(__name__)

#: Per-subscriber backlog. A slow browser drops old notifications rather than
#: applying back-pressure to ingest.
QUEUE_SIZE = 16


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()
        self._last: dict[str, Any] | None = None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def last_event(self) -> dict[str, Any] | None:
        return self._last

    async def publish(self, event: dict[str, Any]) -> None:
        self._last = event
        async with self._lock:
            targets = list(self._subscribers)
        for queue in targets:
            if queue.full():
                with suppress(asyncio.QueueEmpty):  # racing consumer, harmless
                    queue.get_nowait()
            with suppress(asyncio.QueueFull):  # racing producer, harmless
                queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)
