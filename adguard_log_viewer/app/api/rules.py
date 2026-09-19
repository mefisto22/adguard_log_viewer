"""Automatic categorisation rules."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import DbDep, StateDep, ok
from app.categorization.engine import CategorizationEngine, CategoryRule
from app.i18n import Message, detail_of
from app.schemas.entities import RuleWrite
from app.services import rules_service
from app.services.classification import count_stale_domains

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("")
async def list_rules(db: DbDep, state: StateDep) -> dict[str, Any]:
    def _run(conn: sqlite3.Connection) -> dict[str, Any]:
        return {
            "items": rules_service.list_rules(conn),
            "builtin": rules_service.list_builtin_rules(),
            "pending_reclassification": count_stale_domains(conn, revision=state.ruleset_rev),
        }

    payload = await db.run_read(_run)
    payload["total"] = len(payload["items"])
    return payload


@router.post("", status_code=201)
async def create_rule(payload: RuleWrite, db: DbDep, state: StateDep) -> dict[str, Any]:
    try:
        rule_id = await db.run_write(
            lambda conn: rules_service.create_rule(conn, payload.model_dump())
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    except sqlite3.IntegrityError as err:
        raise HTTPException(
            status_code=409, detail=Message("A rule with that name already exists")
        ) from err
    state.reload_engine()
    return ok(id=rule_id)


@router.put("/{rule_id}")
async def update_rule(
    rule_id: int, payload: RuleWrite, db: DbDep, state: StateDep
) -> dict[str, Any]:
    try:
        changed = await db.run_write(
            lambda conn: rules_service.update_rule(conn, rule_id, payload.model_dump())
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=detail_of(err)) from err
    except sqlite3.IntegrityError as err:
        raise HTTPException(
            status_code=409, detail=Message("A rule with that name already exists")
        ) from err
    if not changed:
        raise HTTPException(status_code=404, detail=Message("Rule not found"))
    state.reload_engine()
    return ok()


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int, db: DbDep, state: StateDep) -> dict[str, Any]:
    removed = await db.run_write(lambda conn: rules_service.delete_rule(conn, rule_id))
    if not removed:
        raise HTTPException(status_code=404, detail=Message("Rule not found"))
    state.reload_engine()
    return ok()


@router.post("/test")
async def test_rule(payload: dict[str, Any], state: StateDep) -> dict[str, Any]:
    """Try a rule — saved or draft — against a domain before committing to it."""
    domain = str(payload.get("domain") or "").strip()
    if not domain:
        raise HTTPException(status_code=400, detail=Message("A domain is required"))

    draft = payload.get("rule")
    if isinstance(draft, dict):
        rule = CategoryRule.from_dict({**draft, "builtin": False})
        if rule is None:
            raise HTTPException(
                status_code=400,
                detail=Message(
                    "The rule needs a name, at least one condition and at least one tag"
                ),
            )
        engine = CategorizationEngine([rule])
        return {
            "domain": domain,
            "matched": bool(engine.classify(domain)),
            "tags": [tag.as_dict() for tag in engine.classify(domain)],
            "matches": engine.explain(domain),
        }

    if state.engine is None:
        raise HTTPException(
            status_code=503, detail=Message("The categorisation engine is not ready")
        )
    return {
        "domain": domain,
        "matched": bool(state.engine.classify(domain)),
        "tags": [tag.as_dict() for tag in state.engine.classify(domain)],
        "matches": state.engine.explain(domain),
    }
