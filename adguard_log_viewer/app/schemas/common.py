"""Request models shared by the query, dashboard and detail endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.timeutil import NAMED_RANGES, parse_time_expression
from app.filters.fields import QUICK_SEARCH_FIELDS
from app.filters.nodes import (
    FilterNode,
    Group,
    Predicate,
    combine,
    parse_filter,
    quick_search_filter,
)

SearchMode = Literal["any", "all"]


class SearchSpec(BaseModel):
    """The multi-term quick search.

    ``mode='any'`` is the common case: give it ``["googl", "youtube",
    "googlevideo"]`` and every query matching at least one term comes back.
    """

    model_config = ConfigDict(extra="forbid")

    terms: list[str] = Field(default_factory=list)
    mode: SearchMode = "any"
    fields: list[str] = Field(default_factory=lambda: list(QUICK_SEARCH_FIELDS))
    operator: str = "contains"

    def to_node(self) -> FilterNode | None:
        fields = tuple(self.fields) or QUICK_SEARCH_FIELDS
        return quick_search_filter(
            self.terms, mode=self.mode, fields=fields, operator=self.operator
        )


class TimeWindow(BaseModel):
    """Either a named range, or an explicit from/to pair."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    range: str | None = None
    from_: str | int | float | None = Field(default=None, alias="from")
    to: str | int | float | None = None

    def resolve(self) -> tuple[int | None, int | None]:
        if self.from_ is not None or self.to is not None:
            return (
                parse_time_expression(self.from_),
                parse_time_expression(self.to),
            )
        if self.range:
            span = NAMED_RANGES.get(self.range)
            if span is None:
                # Not a named range: try to read it as a relative expression.
                return parse_time_expression(self.range), None
            if span == 0:
                return None, None
            return parse_time_expression(f"now-{span}s"), None
        return None, None


class FilterRequest(BaseModel):
    """Everything that narrows a result set."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    filter: dict[str, Any] | list[Any] | None = None
    search: SearchSpec | None = None
    window: TimeWindow | None = None
    range: str | None = None
    from_: str | int | float | None = Field(default=None, alias="from")
    to: str | int | float | None = None
    saved_filter_id: int | None = None

    def time_window(self) -> TimeWindow:
        if self.window is not None:
            return self.window
        return TimeWindow.model_validate(
            {"range": self.range, "from": self.from_, "to": self.to}
        )

    def to_node(self, *, saved_filter: Any = None, include_time: bool = True) -> FilterNode | None:
        """Combine every part of the request into one filter tree.

        The parts are ANDed together: the advanced filter, the quick search,
        a saved filter and the time window all have to hold.
        """
        nodes: list[FilterNode | None] = [parse_filter(self.filter)]
        if saved_filter is not None:
            nodes.append(parse_filter(saved_filter))
        if self.search is not None:
            nodes.append(self.search.to_node())
        if include_time:
            from_ns, to_ns = self.time_window().resolve()
            if from_ns is not None:
                nodes.append(Predicate(field="timestamp", operator="gte", value=from_ns))
            if to_ns is not None:
                nodes.append(Predicate(field="timestamp", operator="lt", value=to_ns))
        return combine(nodes, "and")


class QueryListRequest(FilterRequest):
    """Paging and ordering on top of :class:`FilterRequest`."""

    limit: int = 100
    offset: int = 0
    sort: str = "time"
    direction: Literal["asc", "desc"] = "desc"
    include_total: bool = True
    before_id: int | None = None
    after_id: int | None = None


class DashboardRequest(FilterRequest):
    top_limit: int = 10
    buckets: int = 60
    #: Which widgets to compute. Empty means all of them.
    parts: list[str] = Field(default_factory=list)


__all__ = [
    "DashboardRequest",
    "FilterRequest",
    "Group",
    "QueryListRequest",
    "SearchSpec",
    "TimeWindow",
]
