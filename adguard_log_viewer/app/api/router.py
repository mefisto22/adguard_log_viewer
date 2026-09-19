"""Assembles every router under ``/api``."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    dashboard,
    devices,
    domains,
    queries,
    rules,
    saved_filters,
    settings,
    stream,
    system,
    tags,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(system.router)
api_router.include_router(queries.router)
api_router.include_router(dashboard.router)
api_router.include_router(devices.router)
api_router.include_router(domains.router)
api_router.include_router(tags.router)
api_router.include_router(rules.router)
api_router.include_router(saved_filters.router)
api_router.include_router(settings.router)
api_router.include_router(stream.router)

__all__ = ["api_router"]
