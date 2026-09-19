"""Time helpers.

Timestamps are stored as **nanoseconds since the Unix epoch** (``ts_ns``). That
matches AdGuard's own resolution, keeps ordering stable for records logged in
the same millisecond, and dedupes reliably.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

NS_PER_SECOND = 1_000_000_000
NS_PER_MS = 1_000_000

_RELATIVE = re.compile(r"^now\s*(?:([+-])\s*(\d+)\s*([smhdw]))?$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

#: Named ranges offered by the UI, in seconds. ``0`` means "everything".
NAMED_RANGES: dict[str, int] = {
    "15m": 15 * 60,
    "1h": 3600,
    "6h": 6 * 3600,
    "24h": 86400,
    "7d": 7 * 86400,
    "30d": 30 * 86400,
    "90d": 90 * 86400,
    "all": 0,
}


def now_ns() -> int:
    return time.time_ns()


def to_ns(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * NS_PER_SECOND)


def from_ns(ts_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_ns / NS_PER_SECOND, tz=UTC)


def iso_from_ns(ts_ns: int) -> str:
    return from_ns(ts_ns).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> int:
    """Parse an AdGuard/ISO-8601 timestamp into nanoseconds.

    AdGuard reports RFC3339 with nanosecond precision
    (``2024-05-01T10:11:12.123456789Z``). ``datetime.fromisoformat`` truncates
    to microseconds, so the sub-microsecond digits are recovered by hand to keep
    the dedup key exact.
    """
    text = value.strip()
    if not text:
        raise ValueError("empty timestamp")

    nanos_extra = 0
    match = re.search(r"\.(\d+)", text)
    if match:
        digits = match.group(1)
        if len(digits) > 6:
            nanos_extra = int(digits[6:9].ljust(3, "0"))
            text = text[: match.start(1)] + digits[:6] + text[match.end(1) :]

    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"

    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return to_ns(dt) + nanos_extra


def parse_time_expression(
    value: str | int | float | None, *, default: int | None = None
) -> int | None:
    """Resolve a filter time value to ``ts_ns``.

    Accepts:
      * ``"now"``, ``"now-24h"``, ``"now+15m"`` (units: s, m, h, d, w)
      * an ISO-8601 timestamp
      * a number: seconds if < 1e12, milliseconds if < 1e15, else nanoseconds
    """
    if value is None or value == "":
        return default

    if isinstance(value, (int, float)):
        number = float(value)
        if number < 1e12:
            return int(number * NS_PER_SECOND)
        if number < 1e15:
            return int(number * NS_PER_MS)
        return int(number)

    text = str(value).strip()
    relative = _RELATIVE.match(text)
    if relative:
        base = now_ns()
        if relative.group(1) is None:
            return base
        sign = -1 if relative.group(1) == "-" else 1
        amount = int(relative.group(2))
        unit = _UNIT_SECONDS[relative.group(3).lower()]
        return base + sign * amount * unit * NS_PER_SECOND

    if text in NAMED_RANGES:
        span = NAMED_RANGES[text]
        return None if span == 0 else now_ns() - span * NS_PER_SECOND

    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return parse_time_expression(float(text), default=default)

    try:
        return parse_timestamp(text)
    except ValueError:
        return default


def range_to_ns(range_name: str) -> tuple[int | None, int | None]:
    """Turn a named range into ``(from_ns, to_ns)``."""
    span = NAMED_RANGES.get(range_name)
    if span is None:
        return None, None
    if span == 0:
        return None, None
    return now_ns() - span * NS_PER_SECOND, None


def minute_bucket(ts_ns: int) -> int:
    """Unix seconds floored to the start of the containing minute."""
    return (ts_ns // NS_PER_SECOND) // 60 * 60
