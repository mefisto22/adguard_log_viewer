"""Dashboard aggregations."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbDep
from app.schemas.common import DashboardRequest
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _window(request: DashboardRequest) -> tuple[int | None, int | None]:
    return request.time_window().resolve()


@router.post("")
async def dashboard(request: DashboardRequest, db: DbDep) -> dict[str, Any]:
    """Every dashboard widget in one round trip.

    The parts are independent queries, so they run concurrently on separate
    read connections. SQLite releases the GIL while executing, and WAL lets
    readers work in parallel, so a wide time range costs roughly as much as its
    slowest part rather than the sum of all of them.
    """
    from_ns, to_ns = _window(request)
    node = request.to_node(include_time=False)

    requested = request.parts or list(dashboard_service.DEFAULT_PARTS)
    unknown = [part for part in requested if part not in dashboard_service.PART_BUILDERS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown dashboard part: {unknown[0]}")

    async def _part(name: str) -> tuple[str, Any]:
        value = await db.run_read(
            lambda conn: dashboard_service.build_part(
                conn,
                name,
                filter_node=node,
                from_ns=from_ns,
                to_ns=to_ns,
                top_limit=request.top_limit,
                buckets=request.buckets,
            )
        )
        return name, value

    results = await asyncio.gather(*(_part(name) for name in requested))
    return dict(results)


@router.get("")
async def dashboard_get(
    db: DbDep,
    range_: Annotated[str, Query(alias="range")] = "24h",
    top_limit: int = 10,
    buckets: int = 60,
) -> dict[str, Any]:
    return await dashboard(
        DashboardRequest.model_validate(
            {"range": range_, "top_limit": top_limit, "buckets": buckets}
        ),
        db,
    )


@router.post("/timeline")
async def timeline(request: DashboardRequest, db: DbDep) -> dict[str, Any]:
    from_ns, to_ns = _window(request)
    node = request.to_node(include_time=False)
    return await db.run_read(
        lambda conn: dashboard_service.timeline(
            conn, filter_node=node, from_ns=from_ns, to_ns=to_ns, buckets=request.buckets
        )
    )


@router.post("/summary")
async def summary(request: DashboardRequest, db: DbDep) -> dict[str, Any]:
    from_ns, to_ns = _window(request)
    node = request.to_node(include_time=False)
    return await db.run_read(
        lambda conn: dashboard_service.summary(
            conn, filter_node=node, from_ns=from_ns, to_ns=to_ns
        )
    )
