"""Settings, both the read-only add-on options and the editable app settings."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import DbDep, StateDep, ok
from app.i18n import detail_of
from app.schemas.entities import SettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(db: DbDep, state: StateDep) -> dict[str, Any]:
    return await db.run_read(lambda conn: settings_service.describe(conn, state.settings))


@router.patch("")
async def update_settings(
    payload: SettingsUpdate, db: DbDep, state: StateDep
) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> dict[str, Any]:
        settings_service.update(conn, payload.values)
        return settings_service.describe(conn, state.settings)

    try:
        return ok(await db.run_write(_run))
    except settings_service.SettingsError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
