"""Saved filters."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import DbDep, ok
from app.filters.nodes import FilterError
from app.i18n import Message, detail_of
from app.schemas.entities import SavedFilterCreate, SavedFilterUpdate
from app.services import saved_filter_service
from app.services.saved_filter_service import EMPTY_FILTER_MESSAGE

router = APIRouter(prefix="/saved-filters", tags=["saved-filters"])


@router.get("")
async def list_saved_filters(db: DbDep) -> dict[str, Any]:
    items = await db.run_read(saved_filter_service.list_saved_filters)
    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
async def create_saved_filter(payload: SavedFilterCreate, db: DbDep) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> int:
        return saved_filter_service.create_saved_filter(
            conn,
            name=payload.name,
            filter_payload=payload.filter,
            description=payload.description,
        )

    try:
        filter_id = await db.run_write(_run)
    except FilterError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    except ValueError as err:
        status = 400 if str(err) == EMPTY_FILTER_MESSAGE else 409
        raise HTTPException(status_code=status, detail=detail_of(err)) from err
    except sqlite3.IntegrityError as err:
        raise HTTPException(status_code=409, detail=Message("That name is already taken")) from err
    return ok(id=filter_id)


@router.put("/{filter_id}")
async def update_saved_filter(
    filter_id: int, payload: SavedFilterUpdate, db: DbDep
) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> bool:
        return saved_filter_service.update_saved_filter(
            conn,
            filter_id,
            name=payload.name,
            filter_payload=payload.filter,
            description=payload.description,
        )

    try:
        changed = await db.run_write(_run)
    except FilterError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    except sqlite3.IntegrityError as err:
        raise HTTPException(status_code=409, detail=Message("That name is already taken")) from err
    if not changed:
        raise HTTPException(status_code=404, detail=Message("Saved filter not found"))
    return ok()


@router.delete("/{filter_id}")
async def delete_saved_filter(filter_id: int, db: DbDep) -> dict[str, Any]:
    removed = await db.run_write(
        lambda conn: saved_filter_service.delete_saved_filter(conn, filter_id)
    )
    if not removed:
        raise HTTPException(status_code=404, detail=Message("Saved filter not found"))
    return ok()
