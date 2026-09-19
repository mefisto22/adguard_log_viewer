"""Status, health and metadata endpoints."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

from app import __version__
from app.api.deps import DbDep, StateDep, ok
from app.categorization.matchers import OPERATORS as MATCH_OPERATORS
from app.common.timeutil import NAMED_RANGES, now_ns
from app.db.migrations import current_version, target_version
from app.filters.fields import all_fields
from app.ingest.records import RESULT_KINDS
from app.services import settings_service
from app.services.classification import count_stale_domains
from app.services.retention import cleanup

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, Any]:
    """Cheap liveness probe, also used as the add-on watchdog target."""
    return {"status": "ok", "version": __version__, "at_ns": now_ns()}


@router.get("/status")
async def status(db: DbDep, state: StateDep) -> dict[str, Any]:
    status = await state.provider_status()
    provider_status = status.as_dict() if status else None

    def _counts(conn: sqlite3.Connection) -> dict[str, Any]:
        row = conn.execute(
            "SELECT COUNT(*) AS queries, MIN(ts_ns) AS oldest, MAX(ts_ns) AS newest FROM queries"
        ).fetchone()
        return {
            "queries": int(row["queries"]),
            "oldest_ns": row["oldest"],
            "newest_ns": row["newest"],
            "domains": int(conn.execute("SELECT COUNT(*) AS n FROM domains").fetchone()["n"]),
            "clients": int(conn.execute("SELECT COUNT(*) AS n FROM clients").fetchone()["n"]),
            "persons": int(conn.execute("SELECT COUNT(*) AS n FROM persons").fetchone()["n"]),
            "tags": int(conn.execute("SELECT COUNT(*) AS n FROM tags").fetchone()["n"]),
            "rules": int(conn.execute("SELECT COUNT(*) AS n FROM rules").fetchone()["n"]),
            "pending_reclassification": count_stale_domains(conn, revision=state.ruleset_rev),
            "schema_version": current_version(conn),
            "retention_days": settings_service.effective_retention_days(conn, state.settings),
            "ingest_enabled": settings_service.ingest_enabled(conn, state.settings),
        }

    counts = await db.run_read(_counts)

    return {
        "version": __version__,
        "schema_target": target_version(),
        "started_at_ns": state.started_at_ns,
        "database": {**state.db.stats(), **counts},
        "provider": provider_status,
        "discovery": state.discovery.as_dict() if state.discovery else None,
        "ingest": {
            "last": state.last_ingest,
            "error": state.ingest_error,
            "engine_rules": state.engine.rule_count if state.engine else 0,
            "ruleset_rev": state.ruleset_rev,
        },
        "stream": {"subscribers": state.events.subscriber_count},
    }


@router.get("/meta")
async def meta() -> dict[str, Any]:
    """Everything the filter builder needs to render itself."""
    return {
        "fields": [spec.as_dict() for spec in all_fields()],
        "ranges": list(NAMED_RANGES),
        "result_kinds": list(RESULT_KINDS),
        "rule_operators": list(MATCH_OPERATORS),
        "version": __version__,
    }


@router.post("/ingest/run")
async def trigger_ingest(state: StateDep) -> dict[str, Any]:
    """Poll AdGuard right now instead of waiting for the next interval."""
    if state.ingestor is None:
        raise HTTPException(status_code=503, detail="The ingest loop is not running")
    state.ingestor.trigger()
    return ok(triggered=True)


@router.post("/maintenance/cleanup")
async def run_cleanup(db: DbDep, state: StateDep) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> dict[str, int]:
        days = settings_service.effective_retention_days(conn, state.settings)
        return cleanup(conn, days).as_dict()

    return ok(await db.run_write(_run))


@router.post("/maintenance/reclassify")
async def reclassify(db: DbDep, state: StateDep) -> dict[str, Any]:
    """Mark every domain for re-classification against the current rules."""

    def _run(conn: sqlite3.Connection) -> int:
        cursor = conn.execute("UPDATE domains SET ruleset_rev = -1")
        return cursor.rowcount or 0

    state.reload_engine()
    marked = await db.run_write(_run)
    if state.ingestor is not None:
        state.ingestor.trigger()
    return ok(marked=marked)


@router.post("/maintenance/reconnect")
async def reconnect(state: StateDep) -> dict[str, Any]:
    """Re-run AdGuard discovery, for instance after fixing its port."""
    await state.rebuild_provider()
    status = await state.provider_status(force=True)
    status_payload = status.as_dict() if status else None
    return ok(
        provider=status_payload,
        discovery=state.discovery.as_dict() if state.discovery else None,
    )
