"""The filter model.

A filter is a tree of :class:`Group` (``and`` / ``or`` / ``not``) and
:class:`Predicate` leaves. The same tree backs the quick-search box, the
advanced filter builder and saved filters, so there is exactly one code path
from "what the user asked for" to SQL.

    {"op": "and", "children": [
        {"op": "or", "children": [
            {"field": "domain", "operator": "contains", "value": "youtube"},
            {"field": "domain", "operator": "contains", "value": "googlevideo"}]},
        {"field": "timestamp", "operator": "gte", "value": "now-24h"}]}
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from app.filters.fields import QUICK_SEARCH_FIELDS, get_field

#: Guard rails against a pathological filter arriving over the API.
MAX_DEPTH = 10
MAX_NODES = 512

#: A regular expression is evaluated per row; an enormous pattern is never a
#: genuine filter, and rejecting it early keeps the query planner honest.
MAX_REGEX_LENGTH = 500

GROUP_OPS: frozenset[str] = frozenset({"and", "or", "not"})

VALUELESS_OPERATORS: frozenset[str] = frozenset({"is_empty", "is_not_empty"})
LIST_OPERATORS: frozenset[str] = frozenset({"in", "not_in"})


class FilterError(ValueError):
    """The supplied filter is not valid. Surfaced to the client as HTTP 400."""


@dataclass(slots=True)
class Predicate:
    field: str
    operator: str
    value: Any = None
    values: list[Any] = dataclass_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"field": self.field, "operator": self.operator}
        if self.operator in LIST_OPERATORS:
            payload["values"] = list(self.values)
        elif self.operator not in VALUELESS_OPERATORS:
            payload["value"] = self.value
        return payload


@dataclass(slots=True)
class Group:
    op: str
    children: list[FilterNode] = dataclass_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"op": self.op, "children": [child.as_dict() for child in self.children]}


FilterNode = Group | Predicate


def _parse_node(raw: Any, depth: int, budget: list[int]) -> FilterNode:
    if depth > MAX_DEPTH:
        raise FilterError(f"Filter is nested deeper than {MAX_DEPTH} levels")
    budget[0] -= 1
    if budget[0] < 0:
        raise FilterError(f"Filter has more than {MAX_NODES} nodes")

    if not isinstance(raw, dict):
        raise FilterError("Each filter node must be an object")

    op = str(raw.get("op") or "").strip().lower()
    if op:
        if op not in GROUP_OPS:
            raise FilterError(f"Unknown group operator {op!r}")
        children_raw = raw.get("children")
        if not isinstance(children_raw, list):
            raise FilterError(f"Group {op!r} needs a 'children' array")
        children = [_parse_node(child, depth + 1, budget) for child in children_raw]
        if op == "not" and len(children) != 1:
            raise FilterError("'not' takes exactly one child")
        return Group(op=op, children=children)

    field_name = str(raw.get("field") or "").strip().lower()
    if not field_name:
        raise FilterError("A condition needs a 'field'")
    spec = get_field(field_name)
    if spec is None:
        raise FilterError(f"Unknown filter field {field_name!r}")

    operator = str(raw.get("operator") or "equals").strip().lower()
    if operator not in spec.operators:
        raise FilterError(
            f"Operator {operator!r} is not valid for field {spec.name!r}; "
            f"allowed: {', '.join(spec.operators)}"
        )

    if operator in LIST_OPERATORS:
        values = raw.get("values")
        if values is None and raw.get("value") is not None:
            values = raw["value"]
        if isinstance(values, str):
            values = [part.strip() for part in values.split(",") if part.strip()]
        if not isinstance(values, list) or not values:
            raise FilterError(f"Operator {operator!r} needs a non-empty 'values' array")
        if len(values) > 500:
            raise FilterError("A list condition may not hold more than 500 values")
        return Predicate(field=spec.name, operator=operator, values=list(values))

    if operator in VALUELESS_OPERATORS:
        return Predicate(field=spec.name, operator=operator)

    value = raw.get("value")
    if value is None or (isinstance(value, str) and not value.strip()):
        raise FilterError(f"Condition on {spec.name!r} needs a 'value'")
    if operator in ("regex", "not_regex") and len(str(value)) > MAX_REGEX_LENGTH:
        raise FilterError(
            f"A regular expression may not be longer than {MAX_REGEX_LENGTH} characters"
        )
    return Predicate(field=spec.name, operator=operator, value=value)


def parse_filter(raw: Any) -> FilterNode | None:
    """Validate and normalise a filter tree. ``None`` means "no filter"."""
    if raw is None:
        return None
    if isinstance(raw, list):
        raw = {"op": "and", "children": raw}
    if isinstance(raw, dict) and not raw:
        return None
    node = _parse_node(raw, 0, [MAX_NODES])
    return prune(node)


def prune(node: FilterNode | None) -> FilterNode | None:
    """Drop empty groups so they do not turn into stray ``AND ()``."""
    if node is None:
        return None
    if isinstance(node, Predicate):
        return node
    children = [child for child in (prune(child) for child in node.children) if child is not None]
    if not children:
        return None
    if node.op != "not" and len(children) == 1:
        return children[0]
    return Group(op=node.op, children=children)


def combine(nodes: list[FilterNode | None], op: str = "and") -> FilterNode | None:
    """Join several optional filters with ``and``/``or``."""
    present = [node for node in nodes if node is not None]
    if not present:
        return None
    if len(present) == 1:
        return present[0]
    return Group(op=op, children=present)


def quick_search_filter(
    terms: list[str],
    *,
    mode: str = "any",
    fields: tuple[str, ...] = QUICK_SEARCH_FIELDS,
    operator: str = "contains",
) -> FilterNode | None:
    """Build the tree behind the multi-term search box.

    ``mode='any'`` returns records matching **at least one** term (the
    ``googl`` / ``youtube`` / ``googlevideo`` case); ``mode='all'`` requires
    every term. A single term matches across all of *fields*.
    """
    cleaned = [term.strip() for term in terms if term and term.strip()]
    if not cleaned:
        return None

    per_term: list[FilterNode] = []
    for term in cleaned:
        alternatives: list[FilterNode] = [
            Predicate(field=name, operator=operator, value=term) for name in fields
        ]
        per_term.append(
            Group(op="or", children=alternatives) if len(alternatives) > 1 else alternatives[0]
        )

    if len(per_term) == 1:
        return per_term[0]
    return Group(op="or" if mode == "any" else "and", children=per_term)
