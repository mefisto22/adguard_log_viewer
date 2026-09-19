"""Tags and categories."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import DbDep, ok
from app.i18n import Message, detail_of
from app.schemas.entities import TagCreate, TagUpdate
from app.services import tag_service

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("")
async def list_tags(db: DbDep, kind: str | None = None) -> dict[str, Any]:
    items = await db.run_read(lambda conn: tag_service.list_tags(conn, kind=kind))
    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
async def create_tag(payload: TagCreate, db: DbDep) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> int:
        return tag_service.create_tag(
            conn,
            name=payload.name,
            kind=payload.kind,
            color=payload.color,
            description=payload.description,
        )

    try:
        tag_id = await db.run_write(_run)
    except ValueError as err:
        raise HTTPException(status_code=409, detail=detail_of(err)) from err
    return ok(id=tag_id)


@router.patch("/{tag_id}")
async def update_tag(tag_id: int, payload: TagUpdate, db: DbDep) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> bool:
        return tag_service.update_tag(
            conn, tag_id, name=payload.name, color=payload.color, description=payload.description
        )

    try:
        changed = await db.run_write(_run)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    except sqlite3.IntegrityError as err:
        raise HTTPException(
            status_code=409, detail=Message("A tag with that name already exists")
        ) from err
    if not changed:
        raise HTTPException(status_code=404, detail=Message("Tag not found or nothing to change"))
    return ok()


@router.delete("/{tag_id}")
async def delete_tag(tag_id: int, db: DbDep) -> dict[str, Any]:
    try:
        removed = await db.run_write(lambda conn: tag_service.delete_tag(conn, tag_id))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    if not removed:
        raise HTTPException(status_code=404, detail=Message("Tag not found"))
    return ok()
