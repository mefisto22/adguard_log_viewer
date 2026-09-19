"""Translate a filter tree into parameterised SQL.

Every user-supplied value becomes a bound parameter — no value is ever
interpolated into the statement text, so a filter cannot inject SQL. Column
names come only from the fixed :mod:`app.filters.fields` table.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.common.timeutil import parse_time_expression
from app.filters.fields import NEGATIVE_OPERATORS, FieldSpec, get_field, positive_operator
from app.filters.nodes import FilterError, FilterNode, Group, Predicate
from app.i18n import Message
from app.ingest.records import reasons_for_kind

#: Alias the queries table is given in every statement the builder targets.
QUERY_ALIAS = "q"

_LIKE_ESCAPE = "\\"


@dataclass(slots=True)
class CompiledFilter:
    """A ``WHERE`` fragment plus its bound parameters."""

    sql: str
    params: list[object]

    @property
    def is_empty(self) -> bool:
        return self.sql in ("", "1")

    def where(self) -> str:
        """``WHERE ...`` or an empty string when nothing is constrained."""
        return "" if self.is_empty else f"WHERE {self.sql}"

    def and_where(self, extra: str) -> str:
        """Combine with a caller-supplied predicate."""
        if self.is_empty:
            return f"WHERE {extra}" if extra else ""
        return f"WHERE {self.sql} AND ({extra})" if extra else f"WHERE {self.sql}"


def _escape_like(value: str) -> str:
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def _text_predicate(column: str, operator: str, value: object, params: list[object]) -> str:
    text = "" if value is None else str(value)

    if operator == "equals":
        params.append(text)
        return f"{column} = ? COLLATE NOCASE"
    if operator == "contains":
        params.append(f"%{_escape_like(text)}%")
        return f"{column} LIKE ? ESCAPE '{_LIKE_ESCAPE}'"
    if operator == "startswith":
        params.append(f"{_escape_like(text)}%")
        return f"{column} LIKE ? ESCAPE '{_LIKE_ESCAPE}'"
    if operator == "endswith":
        params.append(f"%{_escape_like(text)}")
        return f"{column} LIKE ? ESCAPE '{_LIKE_ESCAPE}'"
    if operator == "regex":
        params.append(text)
        return f"{column} REGEXP ?"
    if operator == "is_empty":
        return f"({column} IS NULL OR {column} = '')"
    raise FilterError(
        Message("Operator {operator} cannot be applied to a text field", operator=repr(operator))
    )


def _list_predicate(column: str, values: list[object], params: list[object]) -> str:
    if not values:
        raise FilterError(Message("A list condition needs at least one value"))
    placeholders = ", ".join("?" for _ in values)
    params.extend(str(value) for value in values)
    return f"{column} COLLATE NOCASE IN ({placeholders})"


def _number_predicate(
    spec: FieldSpec, column: str, operator: str, predicate: Predicate, params: list[object]
) -> str:
    def convert(raw: object) -> float:
        try:
            return float(raw) * spec.scale  # type: ignore[arg-type]
        except (TypeError, ValueError) as err:
            raise FilterError(
                Message("{field} expects a number, got {value}", field=spec.label, value=repr(raw))
            ) from err

    if operator == "in":
        if not predicate.values:
            raise FilterError(Message("A list condition needs at least one value"))
        placeholders = ", ".join("?" for _ in predicate.values)
        params.extend(convert(value) for value in predicate.values)
        return f"{column} IN ({placeholders})"

    params.append(convert(predicate.value))
    symbols = {"equals": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if operator not in symbols:
        raise FilterError(
            Message(
                "Operator {operator} cannot be applied to a numeric field", operator=repr(operator)
            )
        )
    return f"{column} {symbols[operator]} ?"


def _bool_predicate(column: str, value: object, params: list[object]) -> str:
    truthy = value in (True, 1, "1", "true", "True", "yes", "on")
    params.append(1 if truthy else 0)
    return f"{column} = ?"


def _time_predicate(column: str, operator: str, value: object, params: list[object]) -> str:
    resolved = parse_time_expression(value if isinstance(value, (str, int, float)) else None)
    if resolved is None:
        raise FilterError(Message("Cannot interpret {value} as a point in time", value=repr(value)))
    symbols = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if operator not in symbols:
        raise FilterError(
            Message(
                "Operator {operator} cannot be applied to a time field", operator=repr(operator)
            )
        )
    params.append(resolved)
    return f"{column} {symbols[operator]} ?"


def _result_predicate(column: str, predicate: Predicate, params: list[object]) -> str:
    """``result`` is derived from the AdGuard reason, so expand it to a set."""
    kinds = predicate.values if predicate.operator in ("in", "not_in") else [predicate.value]
    reasons: list[str] = []
    for kind in kinds:
        reasons.extend(reasons_for_kind(str(kind).strip().lower()))
    if not reasons:
        raise FilterError(Message("Unknown result kind"))
    placeholders = ", ".join("?" for _ in reasons)
    params.extend(reasons)
    return f"{column} IN ({placeholders})"


def _compile_predicate(predicate: Predicate, params: list[object]) -> str:
    spec = get_field(predicate.field)
    if spec is None:  # pragma: no cover - parse_filter already rejected this
        raise FilterError(Message("Unknown filter field {field}", field=repr(predicate.field)))

    operator = positive_operator(predicate.operator)
    negate = predicate.operator in NEGATIVE_OPERATORS

    inner_params: list[object] = []

    if spec.name == "result":
        column = f"{QUERY_ALIAS}.{spec.column}"
        sql = _result_predicate(column, predicate, inner_params)
    elif spec.fk and spec.subquery and spec.inner_column:
        inner = _leaf_sql(spec, spec.inner_column, operator, predicate, inner_params)
        membership = "NOT IN" if negate else "IN"
        params.extend(inner_params)
        return f"{QUERY_ALIAS}.{spec.fk} {membership} ({spec.subquery}{inner})"
    else:
        if not spec.column:  # pragma: no cover - defensive
            raise FilterError(Message("Field {field} cannot be filtered on", field=repr(spec.name)))
        column = f"{QUERY_ALIAS}.{spec.column}"
        sql = _leaf_sql(spec, column, operator, predicate, inner_params)

    params.extend(inner_params)
    return f"NOT ({sql})" if negate else sql


def _leaf_sql(
    spec: FieldSpec, column: str, operator: str, predicate: Predicate, params: list[object]
) -> str:
    if operator == "in":
        if spec.kind == "number":
            return _number_predicate(spec, column, operator, predicate, params)
        return _list_predicate(column, predicate.values, params)
    if spec.kind == "number":
        return _number_predicate(spec, column, operator, predicate, params)
    if spec.kind == "bool":
        return _bool_predicate(column, predicate.value, params)
    if spec.kind == "time":
        return _time_predicate(column, operator, predicate.value, params)
    return _text_predicate(column, operator, predicate.value, params)


def _merge_key(node: FilterNode) -> tuple[str, str] | None:
    """Key under which OR-ed lookup predicates can share one subquery.

    ``domain contains 'googl' OR domain contains 'youtube'`` would otherwise
    scan the ``domains`` table once per term. Merging them into a single
    ``q.domain_id IN (SELECT ... WHERE a OR b)`` scans it once, which is the
    difference between 450 ms and 150 ms on a large database.
    """
    if not isinstance(node, Predicate):
        return None
    if node.operator in NEGATIVE_OPERATORS:
        return None  # negation is "NOT IN", which cannot be OR-ed together
    spec = get_field(node.field)
    if spec is None or spec.name == "result":
        return None
    if not (spec.fk and spec.subquery and spec.inner_column):
        return None
    return spec.fk, spec.subquery


def _compile_or(node: Group, params: list[object]) -> str:
    """Compile an ``or`` group, merging predicates that share a subquery."""
    buckets: dict[tuple[str, str], list[Predicate]] = {}
    order: list[tuple[str, str] | int] = []
    singles: dict[int, FilterNode] = {}

    for index, child in enumerate(node.children):
        key = _merge_key(child)
        if key is None:
            singles[index] = child
            order.append(index)
            continue
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(child)  # type: ignore[arg-type]

    parts: list[str] = []
    for item in order:
        if isinstance(item, int):
            compiled = _compile_node(singles[item], params)
            if compiled:
                parts.append(compiled)
            continue

        fk, subquery = item
        predicates = buckets[item]
        if len(predicates) == 1:
            parts.append(_compile_predicate(predicates[0], params))
            continue

        inner_parts: list[str] = []
        for predicate in predicates:
            spec = get_field(predicate.field)
            assert spec is not None and spec.inner_column  # guaranteed by _merge_key
            inner_parts.append(
                _leaf_sql(
                    spec,
                    spec.inner_column,
                    positive_operator(predicate.operator),
                    predicate,
                    params,
                )
            )
        parts.append(f"{QUERY_ALIAS}.{fk} IN ({subquery}{' OR '.join(inner_parts)})")

    if not parts:
        return "1"
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def _compile_node(node: FilterNode, params: list[object]) -> str:
    if isinstance(node, Predicate):
        return _compile_predicate(node, params)

    if node.op == "not":
        return f"NOT ({_compile_node(node.children[0], params)})"

    if node.op == "or":
        return _compile_or(node, params)

    parts = [_compile_node(child, params) for child in node.children]
    parts = [part for part in parts if part]
    if not parts:
        return "1"
    if len(parts) == 1:
        return parts[0]
    return "(" + " AND ".join(parts) + ")"


def compile_filter(node: FilterNode | None) -> CompiledFilter:
    """Compile *node* into a ``WHERE`` fragment. ``None`` compiles to ``1``."""
    if node is None:
        return CompiledFilter(sql="1", params=[])
    params: list[object] = []
    sql = _compile_node(node, params)
    return CompiledFilter(sql=sql or "1", params=params)
