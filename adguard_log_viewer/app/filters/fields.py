"""The fields a filter may reference, and what each one maps to in SQL.

Adding a filterable field means adding one entry here — the API schema, the SQL
builder and the field list the UI renders all read from this table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FieldKind = Literal["text", "number", "bool", "time", "enum"]

TEXT_OPERATORS: tuple[str, ...] = (
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "startswith",
    "endswith",
    "regex",
    "not_regex",
    "in",
    "not_in",
    "is_empty",
    "is_not_empty",
)
NUMBER_OPERATORS: tuple[str, ...] = (
    "equals", "not_equals", "gt", "gte", "lt", "lte", "in", "not_in",
)
BOOL_OPERATORS: tuple[str, ...] = ("equals", "not_equals")
TIME_OPERATORS: tuple[str, ...] = ("gt", "gte", "lt", "lte")
ENUM_OPERATORS: tuple[str, ...] = ("equals", "not_equals", "in", "not_in")

#: Operators whose meaning is "the positive form must not hold".
NEGATIVE_OPERATORS: frozenset[str] = frozenset(
    {"not_equals", "not_contains", "not_in", "not_regex", "is_not_empty"}
)


def positive_operator(operator: str) -> str:
    if operator == "is_not_empty":
        return "is_empty"
    if operator.startswith("not_"):
        return operator[4:]
    return operator


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """How one filter field is evaluated.

    ``column`` is a column on the ``queries`` alias ``q``. Fields that live in a
    lookup table instead set ``fk`` (the foreign key on ``q``) plus ``subquery``,
    a ``SELECT`` whose ``WHERE`` clause the builder completes. Resolving those
    against the small lookup tables — a few thousand domains rather than
    millions of queries — is what keeps ``domain contains ...`` fast.
    """

    name: str
    kind: FieldKind
    label: str
    column: str | None = None
    fk: str | None = None
    subquery: str | None = None
    inner_column: str | None = None
    #: Multiplier applied to a numeric value before comparing (ms -> us).
    scale: float = 1.0
    choices: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    description: str = ""

    @property
    def operators(self) -> tuple[str, ...]:
        if self.kind == "number":
            return NUMBER_OPERATORS
        if self.kind == "bool":
            return BOOL_OPERATORS
        if self.kind == "time":
            return TIME_OPERATORS
        if self.kind == "enum":
            return ENUM_OPERATORS
        return TEXT_OPERATORS

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "label": self.label,
            "operators": list(self.operators),
            "choices": list(self.choices),
            "description": self.description,
        }


_DOMAIN_SUB = "SELECT d.id FROM domains d WHERE "
_CLIENT_SUB = "SELECT c.id FROM clients c WHERE "
_PERSON_SUB = (
    "SELECT c.id FROM clients c JOIN persons p ON p.id = c.person_id WHERE "
)
_TAG_SUB = (
    "SELECT dt.domain_id FROM domain_tags dt JOIN tags t ON t.id = dt.tag_id "
    "WHERE t.kind = 'tag' AND "
)
_CATEGORY_SUB = (
    "SELECT dt.domain_id FROM domain_tags dt JOIN tags t ON t.id = dt.tag_id "
    "WHERE t.kind = 'category' AND "
)

FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="domain", kind="text", label="Domain", fk="domain_id",
        subquery=_DOMAIN_SUB, inner_column="d.name",
        aliases=("query", "host", "hostname"),
        description="The queried DNS name.",
    ),
    FieldSpec(
        name="registrable_domain", kind="text", label="Registrable domain", fk="domain_id",
        subquery=_DOMAIN_SUB, inner_column="d.registrable",
        aliases=("root_domain",),
        description="The domain without its subdomains, e.g. youtube.com.",
    ),
    FieldSpec(
        name="client_ip", kind="text", label="Client IP", fk="client_id",
        subquery=_CLIENT_SUB, inner_column="c.ip", aliases=("client", "ip"),
    ),
    FieldSpec(
        name="client_name", kind="text", label="Client name", fk="client_id",
        subquery=_CLIENT_SUB,
        inner_column="COALESCE(NULLIF(c.alias, ''), c.adguard_name)",
        aliases=("device", "device_name"),
        description="Your own alias if set, otherwise the name AdGuard reports.",
    ),
    FieldSpec(
        name="client_id", kind="number", label="Device", column="client_id",
        aliases=("device_id",),
    ),
    FieldSpec(
        name="person", kind="text", label="Person", fk="client_id",
        subquery=_PERSON_SUB, inner_column="p.name", aliases=("user",),
        description="Matches every device assigned to the person.",
    ),
    FieldSpec(
        name="person_id", kind="number", label="Person id", fk="client_id",
        subquery=_CLIENT_SUB, inner_column="c.person_id", aliases=("user_id",),
    ),
    FieldSpec(
        name="tag", kind="text", label="Tag", fk="domain_id",
        subquery=_TAG_SUB, inner_column="t.name",
        description="A tag applied to the domain by a rule or by hand.",
    ),
    FieldSpec(
        name="category", kind="text", label="Category", fk="domain_id",
        subquery=_CATEGORY_SUB, inner_column="t.name",
    ),
    FieldSpec(
        name="query_type", kind="text", label="Query type", column="qtype",
        aliases=("qtype", "type"),
        choices=("A", "AAAA", "CNAME", "PTR", "HTTPS", "SVCB", "TXT", "MX", "NS", "SOA", "SRV"),
    ),
    FieldSpec(name="query_class", kind="text", label="Query class", column="qclass"),
    FieldSpec(
        name="blocked", kind="bool", label="Blocked", column="blocked",
        description="True when AdGuard suppressed the answer.",
    ),
    FieldSpec(name="cached", kind="bool", label="Cached", column="cached"),
    FieldSpec(
        name="response_status", kind="text", label="Response status", column="status",
        aliases=("status", "rcode"),
        choices=("NOERROR", "NXDOMAIN", "SERVFAIL", "REFUSED", "FORMERR", "NOTIMP"),
    ),
    FieldSpec(
        name="reason", kind="text", label="AdGuard reason", column="reason",
        choices=(
            "NotFilteredNotFound", "NotFilteredWhiteList", "NotFilteredError",
            "FilteredBlackList", "FilteredSafeBrowsing", "FilteredParental",
            "FilteredInvalid", "FilteredSafeSearch", "FilteredBlockedService",
            "Rewrite", "RewriteEtcHosts", "RewriteRule",
        ),
    ),
    FieldSpec(
        name="result", kind="enum", label="Result", column="reason",
        choices=("allowed", "blocked", "rewritten", "allowlisted", "error"),
        aliases=("result_kind",),
        description="Coarse outcome derived from the AdGuard reason.",
    ),
    FieldSpec(
        name="rule", kind="text", label="Filter rule", column="rule_text",
        aliases=("rule_text", "filter_rule"),
    ),
    FieldSpec(
        name="filter_list_id", kind="number", label="Filter list id", column="filter_list_id",
    ),
    FieldSpec(name="upstream", kind="text", label="Upstream", column="upstream"),
    FieldSpec(name="answer", kind="text", label="Answer", column="answer"),
    FieldSpec(name="client_proto", kind="text", label="Client protocol", column="client_proto",
              choices=("", "dot", "doh", "doq", "dnscrypt")),
    FieldSpec(
        name="response_time", kind="number", label="Response time (ms)", column="elapsed_us",
        scale=1000.0, aliases=("elapsed_ms", "latency"),
    ),
    FieldSpec(
        name="timestamp", kind="time", label="Time", column="ts_ns",
        aliases=("time", "ts"),
        description="Accepts now-24h, an ISO timestamp, or a number.",
    ),
)

_BY_NAME: dict[str, FieldSpec] = {}
for spec in FIELDS:
    _BY_NAME[spec.name] = spec
    for alias in spec.aliases:
        _BY_NAME.setdefault(alias, spec)


def get_field(name: str) -> FieldSpec | None:
    return _BY_NAME.get(name.strip().lower())


def all_fields() -> tuple[FieldSpec, ...]:
    return FIELDS


#: Fields the quick-search box offers, in the order the UI shows them.
QUICK_SEARCH_FIELDS: tuple[str, ...] = ("domain", "client_ip", "client_name", "answer", "rule")
