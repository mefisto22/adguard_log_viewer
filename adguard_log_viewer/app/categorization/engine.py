"""Domain categorisation engine.

Rules are data, not code: a rule is a name, a match mode, a list of conditions
and a list of tags to apply. Built-in rules ship as JSON next to this module;
user rules live in the database and are merged in at load time. Nothing about a
category is hardcoded in a branch.

Performance
-----------
Classification runs **once per domain**, not once per query — a new domain is
classified when it is first seen, and again only when the rule set changes.
Rules whose conditions are all ``suffix``/``equals`` go into dictionary indexes
and are resolved in O(labels); everything else is a short linear scan.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.categorization.matchers import FIELDS, INDEXED_OPERATORS, OPERATORS, match
from app.common.domains import normalize_domain, parent_domains, registrable_domain

_LOGGER = logging.getLogger(__name__)

BUILTIN_PATH = Path(__file__).with_name("data") / "builtin_rules.json"

TAG_KINDS: tuple[str, ...] = ("tag", "category")


@dataclass(frozen=True, slots=True)
class Condition:
    field: str = "domain"
    operator: str = "suffix"
    value: str = ""

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Condition | None:
        field_name = str(raw.get("field") or "domain").strip().lower()
        operator = str(raw.get("operator") or "suffix").strip().lower()
        value = str(raw.get("value") or "").strip()
        if field_name not in FIELDS or operator not in OPERATORS or not value:
            return None
        return Condition(field=field_name, operator=operator, value=value)

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "operator": self.operator, "value": self.value}

    def evaluate(self, domain: str, registrable: str) -> bool:
        subject = registrable if self.field == "registrable" else domain
        return match(self.operator, subject, self.value)

    @property
    def indexable(self) -> bool:
        return self.field == "domain" and self.operator in INDEXED_OPERATORS


@dataclass(frozen=True, slots=True)
class TagRef:
    name: str
    kind: str = "tag"

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> TagRef | None:
        name = str(raw.get("name") or "").strip()
        kind = str(raw.get("kind") or "tag").strip().lower()
        if not name or kind not in TAG_KINDS:
            return None
        return TagRef(name=name, kind=kind)

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "kind": self.kind}


@dataclass(slots=True)
class CategoryRule:
    name: str
    tags: tuple[TagRef, ...]
    conditions: tuple[Condition, ...]
    id: int = 0
    enabled: bool = True
    priority: int = 100
    match_mode: str = "any"
    builtin: bool = False

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> CategoryRule | None:
        name = str(raw.get("name") or "").strip()
        if not name:
            return None

        conditions = tuple(
            condition
            for condition in (
                Condition.from_dict(item)
                for item in raw.get("conditions") or []
                if isinstance(item, dict)
            )
            if condition is not None
        )
        tags = tuple(
            tag
            for tag in (
                TagRef.from_dict(item) for item in raw.get("tags") or [] if isinstance(item, dict)
            )
            if tag is not None
        )
        if not conditions or not tags:
            return None

        match_mode = str(raw.get("match_mode") or "any").strip().lower()
        if match_mode not in ("any", "all"):
            match_mode = "any"

        return CategoryRule(
            id=int(raw.get("id") or 0),
            name=name,
            enabled=bool(raw.get("enabled", True)),
            priority=int(raw.get("priority") or 100),
            match_mode=match_mode,
            conditions=conditions,
            tags=tags,
            builtin=bool(raw.get("builtin", False)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "priority": self.priority,
            "match_mode": self.match_mode,
            "conditions": [condition.as_dict() for condition in self.conditions],
            "tags": [tag.as_dict() for tag in self.tags],
            "builtin": self.builtin,
        }

    def matches(self, domain: str, registrable: str) -> bool:
        if self.match_mode == "all":
            return all(condition.evaluate(domain, registrable) for condition in self.conditions)
        return any(condition.evaluate(domain, registrable) for condition in self.conditions)

    @property
    def fully_indexable(self) -> bool:
        return self.match_mode == "any" and all(c.indexable for c in self.conditions)


@dataclass(slots=True)
class Ruleset:
    rules: list[CategoryRule] = field(default_factory=list)
    tags: list[TagRef] = field(default_factory=list)


class CategorizationEngine:
    """Applies a rule set to domain names."""

    def __init__(self, rules: Iterable[CategoryRule], *, cache_size: int = 8192) -> None:
        self._rules: list[CategoryRule] = sorted(
            (rule for rule in rules if rule.enabled),
            key=lambda rule: (rule.priority, rule.id, rule.name),
        )
        self._suffix_index: dict[str, list[int]] = {}
        self._equals_index: dict[str, list[int]] = {}
        self._scan: list[int] = []
        self._build_indexes()
        self._classify_cached = lru_cache(maxsize=cache_size)(self._classify_uncached)

    # -- construction -------------------------------------------------------

    def _build_indexes(self) -> None:
        for position, rule in enumerate(self._rules):
            if not rule.fully_indexable:
                self._scan.append(position)
                continue
            for condition in rule.conditions:
                key = normalize_domain(condition.value)
                if not key:
                    continue
                index = self._suffix_index if condition.operator == "suffix" else self._equals_index
                index.setdefault(key, []).append(position)

    @property
    def rules(self) -> Sequence[CategoryRule]:
        return self._rules

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    # -- classification -----------------------------------------------------

    def _classify_uncached(self, domain: str) -> tuple[TagRef, ...]:
        normalized = normalize_domain(domain)
        if not normalized:
            return ()
        registrable = registrable_domain(normalized)

        positions: set[int] = set()

        for candidate in parent_domains(normalized):
            hits = self._suffix_index.get(candidate)
            if hits:
                positions.update(hits)
        hits = self._equals_index.get(normalized)
        if hits:
            positions.update(hits)

        for position in self._scan:
            if self._rules[position].matches(normalized, registrable):
                positions.add(position)

        tags: list[TagRef] = []
        seen: set[tuple[str, str]] = set()
        for position in sorted(positions):
            for tag in self._rules[position].tags:
                key = (tag.name, tag.kind)
                if key not in seen:
                    seen.add(key)
                    tags.append(tag)
        return tuple(tags)

    def classify(self, domain: str) -> tuple[TagRef, ...]:
        """All tags and categories that apply to *domain*."""
        return self._classify_cached(domain)

    def explain(self, domain: str) -> list[dict[str, Any]]:
        """Which rules matched — used by the rule tester in the UI."""
        normalized = normalize_domain(domain)
        if not normalized:
            return []
        registrable = registrable_domain(normalized)
        return [
            {
                "rule": rule.name,
                "rule_id": rule.id,
                "builtin": rule.builtin,
                "tags": [tag.as_dict() for tag in rule.tags],
            }
            for rule in self._rules
            if rule.matches(normalized, registrable)
        ]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as err:
        _LOGGER.error("Cannot read rule set %s: %s", path, err)
        return {}
    return data if isinstance(data, dict) else {}


def load_builtin_ruleset(path: Path | None = None) -> Ruleset:
    """Load the rule set shipped with the add-on.

    The file is bundled in the image; nothing is downloaded at runtime.
    """
    data = _load_json(path or BUILTIN_PATH)
    rules: list[CategoryRule] = []
    for raw in data.get("rules") or []:
        if not isinstance(raw, dict):
            continue
        raw = {**raw, "builtin": True}
        rule = CategoryRule.from_dict(raw)
        if rule is not None:
            rules.append(rule)

    tags: list[TagRef] = []
    for raw in data.get("tags") or []:
        if isinstance(raw, dict):
            tag = TagRef.from_dict(raw)
            if tag is not None:
                tags.append(tag)

    _LOGGER.info("Loaded %d built-in categorisation rules", len(rules))
    return Ruleset(rules=rules, tags=tags)
