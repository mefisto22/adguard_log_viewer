"""Server-Sent Events.

The stream carries notifications only — "N new records, highest id X". The
browser reacts by fetching the delta through the normal filtered query API, so
the full query log is never streamed and the client stays in charge of what it
asks for.

Home Assistant's ingress buffers responses unless the add-on sets
``ingress_stream: true``, which this add-on does.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import StateDep
from app.common.timeutil import now_ns

_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])

#: Comment line sent when nothing happened, so proxies keep the socket open.
HEARTBEAT_SECONDS = 20.0


def _format(event: dict[str, object]) -> str:
    return f"event: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"


@router.get("/stream")
async def stream(request: Request, state: StateDep) -> StreamingResponse:
    async def generator() -> AsyncIterator[str]:
        async with state.events.subscribe() as queue:
            yield _format({"type": "hello", "at_ns": now_ns()})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                except asyncio.CancelledError:
                    break
                yield _format(event)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
