"""Query log listing."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbDep
from app.i18n import Message
from app.schemas.common import QueryListRequest, SearchSpec
from app.services import query_service, saved_filter_service

router = APIRouter(prefix="/queries", tags=["queries"])


def _resolve(conn: sqlite3.Connection, request: QueryListRequest) -> Any:
    saved = None
    if request.saved_filter_id is not None:
        stored = saved_filter_service.get_saved_filter(conn, request.saved_filter_id)
        if stored is None:
            raise HTTPException(status_code=404, detail=Message("Saved filter not found"))
        saved = stored["filter"]
    return request.to_node(saved_filter=saved)


@router.post("/search")
async def search_queries(request: QueryListRequest, db: DbDep) -> dict[str, Any]:
    """List query records matching a full filter tree.

    The POST body carries the advanced filter, the quick search terms, the time
    window and the paging options. Everything is evaluated in SQL.
    """

    def _run(conn: sqlite3.Connection) -> dict[str, Any]:
        node = _resolve(conn, request)
        page = query_service.list_queries(
            conn,
            filter_node=node,
            limit=request.limit,
            offset=request.offset,
            sort=request.sort,
            direction=request.direction,
            include_total=request.include_total,
            before_id=request.before_id,
            after_id=request.after_id,
        )
        return page.as_dict()

    return await db.run_read(_run)


@router.get("")
async def list_queries(
    db: DbDep,
    search: Annotated[str, Query(description="Comma separated search terms")] = "",
    mode: Annotated[str, Query(pattern="^(any|all)$")] = "any",
    fields: Annotated[str, Query(description="Comma separated field names")] = "",
    range_: Annotated[str, Query(alias="range")] = "",
    limit: int = 100,
    offset: int = 0,
    sort: str = "time",
    direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    after_id: int | None = None,
    before_id: int | None = None,
) -> dict[str, Any]:
    """Convenience GET form of the search endpoint."""
    terms = [term.strip() for term in search.split(",") if term.strip()]
    payload: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "sort": sort,
        "direction": direction,
        "after_id": after_id,
        "before_id": before_id,
    }
    if range_:
        payload["range"] = range_
    if terms:
        spec: dict[str, Any] = {"terms": terms, "mode": mode}
        if fields:
            spec["fields"] = [name.strip() for name in fields.split(",") if name.strip()]
        payload["search"] = SearchSpec.model_validate(spec)
    return await search_queries(QueryListRequest.model_validate(payload), db)


@router.get("/{query_id}")
async def get_query(query_id: int, db: DbDep) -> dict[str, Any]:
    item = await db.run_read(lambda conn: query_service.get_query(conn, query_id))
    if item is None:
        raise HTTPException(status_code=404, detail=Message("Query not found"))
    return item
