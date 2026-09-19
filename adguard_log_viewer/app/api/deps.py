"""Shared dependencies for the API routers."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from app.db.database import Database
from app.runtime import AppState


def get_state(request: Request) -> AppState:
    state: AppState | None = getattr(request.app.state, "app_state", None)
    if state is None:  # pragma: no cover - only before startup completes
        raise HTTPException(status_code=503, detail="The application is still starting")
    return state


def get_db(state: Annotated[AppState, Depends(get_state)]) -> Database:
    return state.db


StateDep = Annotated[AppState, Depends(get_state)]
DbDep = Annotated[Database, Depends(get_db)]


def ok(payload: Any = None, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": True}
    if isinstance(payload, dict):
        result.update(payload)
    elif payload is not None:
        result["result"] = payload
    result.update(extra)
    return result
