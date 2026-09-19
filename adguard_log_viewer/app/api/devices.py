"""Devices (clients) and people."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbDep, ok
from app.common.timeutil import parse_time_expression
from app.i18n import Message, detail_of
from app.schemas.entities import DeviceAssign, DeviceUpdate, PersonCreate, PersonUpdate
from app.services import device_service

router = APIRouter(tags=["devices"])


def _window(range_: str, from_: str | None, to: str | None) -> tuple[int | None, int | None]:
    from app.schemas.common import TimeWindow

    return TimeWindow.model_validate({"range": range_, "from": from_, "to": to}).resolve()


# -- devices ----------------------------------------------------------------


@router.get("/devices")
async def list_devices(
    db: DbDep,
    search: str = "",
    person_id: int | None = None,
    sort: str = "query_count",
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    return await db.run_read(
        lambda conn: device_service.list_devices(
            conn, search=search, person_id=person_id, sort=sort, limit=limit, offset=offset
        )
    )


@router.get("/devices/{client_id}")
async def get_device(client_id: int, db: DbDep) -> dict[str, Any]:
    device = await db.run_read(lambda conn: device_service.get_device(conn, client_id))
    if device is None:
        raise HTTPException(status_code=404, detail=Message("Device not found"))
    return device


@router.get("/devices/{client_id}/detail")
async def device_detail(
    client_id: int,
    db: DbDep,
    range_: Annotated[str, Query(alias="range")] = "24h",
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
    top_limit: int = 10,
) -> dict[str, Any]:
    from_ns, to_ns = _window(range_, from_, to)
    detail = await db.run_read(
        lambda conn: device_service.device_detail(
            conn, client_id, from_ns=from_ns, to_ns=to_ns, top_limit=top_limit
        )
    )
    if detail is None:
        raise HTTPException(status_code=404, detail=Message("Device not found"))
    return detail


@router.patch("/devices/{client_id}")
async def update_device(client_id: int, payload: DeviceUpdate, db: DbDep) -> dict[str, Any]:
    changed = await db.run_write(
        lambda conn: device_service.update_device(
            conn,
            client_id,
            alias=payload.alias,
            person_id=payload.person_id,
            clear_person=payload.clear_person,
        )
    )
    if not changed:
        raise HTTPException(
            status_code=404, detail=Message("Device not found or nothing to change")
        )
    device = await db.run_read(lambda conn: device_service.get_device(conn, client_id))
    return ok({"device": device})


@router.delete("/devices/{client_id}")
async def delete_device(client_id: int, db: DbDep) -> dict[str, Any]:
    removed = await db.run_write(lambda conn: device_service.delete_device(conn, client_id))
    if not removed:
        raise HTTPException(status_code=404, detail=Message("Device not found"))
    return ok()


@router.post("/devices/assign")
async def assign_devices(payload: DeviceAssign, db: DbDep) -> dict[str, Any]:
    changed = await db.run_write(
        lambda conn: device_service.assign_devices(conn, payload.person_id, payload.client_ids)
    )
    return ok(changed=changed)


# -- persons ----------------------------------------------------------------


@router.get("/persons")
async def list_persons(db: DbDep) -> dict[str, Any]:
    items = await db.run_read(device_service.list_persons)
    return {"items": items, "total": len(items)}


@router.post("/persons", status_code=201)
async def create_person(payload: PersonCreate, db: DbDep) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> int:
        return device_service.create_person(
            conn, name=payload.name, color=payload.color, note=payload.note
        )

    try:
        person_id = await db.run_write(_run)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    except sqlite3.IntegrityError as err:
        raise HTTPException(
            status_code=409, detail=Message("A person with that name already exists")
        ) from err
    return ok(id=person_id)


@router.patch("/persons/{person_id}")
async def update_person(person_id: int, payload: PersonUpdate, db: DbDep) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> bool:
        return device_service.update_person(
            conn, person_id, name=payload.name, color=payload.color, note=payload.note
        )

    try:
        changed = await db.run_write(_run)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    except sqlite3.IntegrityError as err:
        raise HTTPException(
            status_code=409, detail=Message("A person with that name already exists")
        ) from err
    if not changed:
        raise HTTPException(
            status_code=404, detail=Message("Person not found or nothing to change")
        )
    return ok()


@router.delete("/persons/{person_id}")
async def delete_person(person_id: int, db: DbDep) -> dict[str, Any]:
    removed = await db.run_write(lambda conn: device_service.delete_person(conn, person_id))
    if not removed:
        raise HTTPException(status_code=404, detail=Message("Person not found"))
    return ok()


@router.get("/persons/{person_id}/detail")
async def person_detail(
    person_id: int,
    db: DbDep,
    range_: Annotated[str, Query(alias="range")] = "24h",
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
    top_limit: int = 10,
) -> dict[str, Any]:
    from_ns, to_ns = _window(range_, from_, to)
    detail = await db.run_read(
        lambda conn: device_service.person_detail(
            conn, person_id, from_ns=from_ns, to_ns=to_ns, top_limit=top_limit
        )
    )
    if detail is None:
        raise HTTPException(status_code=404, detail=Message("Person not found"))
    return detail


__all__ = ["parse_time_expression", "router"]
