"""Categorisation rules: the built-in set plus the user's own."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from functools import lru_cache
from typing import Any

from app.categorization.engine import (
    CategorizationEngine,
    CategoryRule,
    Ruleset,
    load_builtin_ruleset,
)
from app.i18n import Message
from app.services.classification import bump_ruleset_rev, seed_tags

_LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def builtin_ruleset() -> Ruleset:
    return load_builtin_ruleset()


def builtin_tag_colors() -> dict[str, str]:
    """Colours declared for the built-in tags, keyed by tag name."""
    from app.categorization.engine import BUILTIN_PATH  # local import keeps the cycle out

    try:
        with BUILTIN_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    colors: dict[str, str] = {}
    for entry in data.get("tags") or []:
        if isinstance(entry, dict) and entry.get("name") and entry.get("color"):
            colors[str(entry["name"])] = str(entry["color"])
    return colors


def _row_to_rule(row: sqlite3.Row) -> CategoryRule | None:
    try:
        conditions = json.loads(row["conditions_json"])
        tags = json.loads(row["tags_json"])
    except (ValueError, TypeError):
        _LOGGER.warning("Rule %s has unreadable JSON and was skipped", row["name"])
        return None
    return CategoryRule.from_dict(
        {
            "id": row["id"],
            "name": row["name"],
            "enabled": bool(row["enabled"]),
            "priority": row["priority"],
            "match_mode": row["match_mode"],
            "conditions": conditions,
            "tags": tags,
            "builtin": bool(row["builtin"]),
        }
    )


def load_user_rules(conn: sqlite3.Connection) -> list[CategoryRule]:
    rules: list[CategoryRule] = []
    for row in conn.execute("SELECT * FROM rules ORDER BY priority, id"):
        rule = _row_to_rule(row)
        if rule is not None:
            rules.append(rule)
    return rules


def build_engine(conn: sqlite3.Connection) -> CategorizationEngine:
    """Engine over the built-in rules plus every enabled user rule.

    User rules get a small id offset so that, at equal priority, they are
    applied after the built-ins.
    """
    builtin = builtin_ruleset()
    rules: list[CategoryRule] = list(builtin.rules)
    rules.extend(load_user_rules(conn))
    return CategorizationEngine(rules)


def seed_builtin_tags(conn: sqlite3.Connection) -> None:
    ruleset = builtin_ruleset()
    seed_tags(conn, ruleset.tags, builtin_tag_colors())


# -- CRUD -------------------------------------------------------------------


def list_rules(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in conn.execute("SELECT * FROM rules ORDER BY priority, id"):
        rule = _row_to_rule(row)
        if rule is None:
            continue
        payload = rule.as_dict()
        payload["created_at"] = row["created_at"]
        payload["updated_at"] = row["updated_at"]
        result.append(payload)
    return result


def list_builtin_rules() -> list[dict[str, Any]]:
    return [rule.as_dict() for rule in builtin_ruleset().rules]


def _validated(payload: dict[str, Any]) -> CategoryRule:
    rule = CategoryRule.from_dict({**payload, "builtin": False})
    if rule is None:
        raise ValueError(
            Message("A rule needs a name, at least one condition and at least one tag")
        )
    return rule


def create_rule(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    rule = _validated(payload)
    now = int(time.time())
    cursor = conn.execute(
        "INSERT INTO rules (name, enabled, priority, match_mode, conditions_json, tags_json, "
        " builtin, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (
            rule.name,
            int(rule.enabled),
            rule.priority,
            rule.match_mode,
            json.dumps([condition.as_dict() for condition in rule.conditions]),
            json.dumps([tag.as_dict() for tag in rule.tags]),
            now,
            now,
        ),
    )
    bump_ruleset_rev(conn)
    return int(cursor.lastrowid or 0)


def update_rule(conn: sqlite3.Connection, rule_id: int, payload: dict[str, Any]) -> bool:
    rule = _validated({**payload, "id": rule_id})
    cursor = conn.execute(
        "UPDATE rules SET name = ?, enabled = ?, priority = ?, match_mode = ?, "
        " conditions_json = ?, tags_json = ?, updated_at = ? WHERE id = ?",
        (
            rule.name,
            int(rule.enabled),
            rule.priority,
            rule.match_mode,
            json.dumps([condition.as_dict() for condition in rule.conditions]),
            json.dumps([tag.as_dict() for tag in rule.tags]),
            int(time.time()),
            rule_id,
        ),
    )
    if cursor.rowcount:
        bump_ruleset_rev(conn)
        return True
    return False


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> bool:
    cursor = conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    if cursor.rowcount:
        bump_ruleset_rev(conn)
        return True
    return False
