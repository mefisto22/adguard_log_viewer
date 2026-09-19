"""The normalised query record shared by every provider.

Whatever the source — AdGuard's HTTP API or its ``querylog.json`` file — it is
converted into a :class:`QueryRecord` before it reaches the rest of the
application. Nothing downstream knows where the data came from.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# AdGuard's filtering reasons, in the numeric order used by the JSON log file.
# Verified against AdguardTeam/AdGuardHome internal/filtering/reason.go.
REASON_NAMES: tuple[str, ...] = (
    "NotFilteredNotFound",      # 0
    "NotFilteredWhiteList",     # 1
    "NotFilteredError",         # 2
    "FilteredBlackList",        # 3
    "FilteredSafeBrowsing",     # 4
    "FilteredParental",         # 5
    "FilteredInvalid",          # 6
    "FilteredSafeSearch",       # 7
    "FilteredBlockedService",   # 8
    "Rewrite",                  # 9
    "RewriteEtcHosts",          # 10
    "RewriteRule",              # 11
)

#: Reasons that mean the answer was suppressed.
BLOCKED_REASONS: frozenset[str] = frozenset(
    {
        "FilteredBlackList",
        "FilteredSafeBrowsing",
        "FilteredParental",
        "FilteredInvalid",
        "FilteredBlockedService",
    }
)

#: Reasons that mean the answer was replaced rather than suppressed.
REWRITTEN_REASONS: frozenset[str] = frozenset(
    {"FilteredSafeSearch", "Rewrite", "RewriteEtcHosts", "RewriteRule"}
)

#: Reasons that mean an explicit allow-list hit.
ALLOWLISTED_REASONS: frozenset[str] = frozenset({"NotFilteredWhiteList"})

#: Coarse outcome used by the UI's "status" filter.
RESULT_KINDS: tuple[str, ...] = ("allowed", "blocked", "rewritten", "allowlisted", "error")


def reason_name(value: object) -> str:
    """Map a reason from either representation to its canonical name."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        if 0 <= value < len(REASON_NAMES):
            return REASON_NAMES[value]
        return ""
    if isinstance(value, str):
        return value.strip()
    return ""


def result_kind(reason: str) -> str:
    if reason in BLOCKED_REASONS:
        return "blocked"
    if reason in REWRITTEN_REASONS:
        return "rewritten"
    if reason in ALLOWLISTED_REASONS:
        return "allowlisted"
    if reason == "NotFilteredError":
        return "error"
    return "allowed"


def reasons_for_kind(kind: str) -> tuple[str, ...]:
    """Inverse of :func:`result_kind`, for building SQL predicates."""
    if kind == "blocked":
        return tuple(sorted(BLOCKED_REASONS))
    if kind == "rewritten":
        return tuple(sorted(REWRITTEN_REASONS))
    if kind == "allowlisted":
        return tuple(sorted(ALLOWLISTED_REASONS))
    if kind == "error":
        return ("NotFilteredError",)
    return ("NotFilteredNotFound", "")


def compute_uid(ts_ns: int, client_ip: str, domain: str, qtype: str) -> int:
    """Stable 64-bit identity for a query log record.

    AdGuard has no record id of its own, so dedup relies on this. The four
    inputs together are unique in practice: AdGuard timestamps have nanosecond
    resolution, and two different queries from the same client for the same
    name and type within the same nanosecond do not happen.

    Returned as a signed 64-bit integer so SQLite can store it in an INTEGER
    column and index it cheaply.
    """
    payload = f"{ts_ns}|{client_ip}|{domain}|{qtype}".encode()
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    unsigned = int.from_bytes(digest, "big")
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


@dataclass(slots=True)
class DnsAnswer:
    type: str = ""
    value: str = ""
    ttl: int = 0

    def as_dict(self) -> dict[str, object]:
        return {"type": self.type, "value": self.value, "ttl": self.ttl}


@dataclass(slots=True)
class QueryRecord:
    """One DNS query as stored by the application."""

    ts_ns: int
    domain: str
    client_ip: str
    qtype: str = ""
    qclass: str = "IN"
    client_name: str = ""
    status: str = ""
    reason: str = ""
    rule_text: str = ""
    filter_list_id: int = -1
    elapsed_us: int = 0
    upstream: str = ""
    cached: bool = False
    client_proto: str = ""
    answers: list[DnsAnswer] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.reason in BLOCKED_REASONS

    @property
    def kind(self) -> str:
        return result_kind(self.reason)

    @property
    def uid(self) -> int:
        return compute_uid(self.ts_ns, self.client_ip, self.domain, self.qtype)

    @property
    def primary_answer(self) -> str:
        for answer in self.answers:
            if answer.value:
                return answer.value
        return ""

    def is_valid(self) -> bool:
        return bool(self.domain) and bool(self.client_ip) and self.ts_ns > 0
