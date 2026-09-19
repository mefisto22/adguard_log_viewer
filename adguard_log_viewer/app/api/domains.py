"""Domains and their details."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbDep, ok
from app.schemas.common import TimeWindow
from app.schemas.entities import DomainTagsUpdate
from app.services import domain_service, tag_service

router = APIRouter(prefix="/domains", tags=["domains"])


@router.get("")
async def list_domains(
    db: DbDep,
    search: str = "",
    sort: str = "query_count",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    return await db.run_read(
        lambda conn: domain_service.list_domains(
            conn, search=search, sort=sort, limit=limit, offset=offset
        )
    )


@router.get("/lookup")
async def lookup_domain(
    name: str,
    db: DbDep,
    range_: Annotated[str, Query(alias="range")] = "24h",
) -> dict[str, Any]:
    from_ns, to_ns = TimeWindow.model_validate({"range": range_}).resolve()
    detail = await db.run_read(
        lambda conn: domain_service.domain_detail(
            conn, name=name, from_ns=from_ns, to_ns=to_ns
        )
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return detail


@router.get("/{domain_id}")
async def domain_detail(
    domain_id: int,
    db: DbDep,
    range_: Annotated[str, Query(alias="range")] = "24h",
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
    top_limit: int = 10,
) -> dict[str, Any]:
    from_ns, to_ns = TimeWindow.model_validate(
        {"range": range_, "from": from_, "to": to}
    ).resolve()
    detail = await db.run_read(
        lambda conn: domain_service.domain_detail(
            conn, domain_id=domain_id, from_ns=from_ns, to_ns=to_ns, top_limit=top_limit
        )
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return detail


@router.put("/{domain_id}/tags")
async def set_domain_tags(
    domain_id: int, payload: DomainTagsUpdate, db: DbDep
) -> dict[str, Any]:
    await db.run_write(lambda conn: tag_service.set_domain_tags(conn, domain_id, payload.tag_ids))
    detail = await db.run_read(lambda conn: domain_service.domain_detail(conn, domain_id=domain_id))
    if detail is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return ok({"domain": detail["domain"]})
