"""How close the process is to its file descriptor limit.

The one outage this app has had came from running out of file descriptors:
``accept()`` failed with EMFILE, the web interface lost its connection, and the
log filled with ten thousand identical tracebacks within a second — so the
entry that would have shown the cause had long scrolled out. Reporting the
count, and warning well before the limit, turns a sudden stop into something
visible while there is still time to act on it.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

try:  # pragma: no cover - always present on Linux and macOS
    import resource
except ImportError:  # pragma: no cover - Windows, which this never runs on
    resource = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

#: Share of the limit at which a warning is written.
WARN_RATIO = 0.8

_DESCRIPTOR_DIRS = ("/proc/self/fd", "/dev/fd")


@dataclass(frozen=True, slots=True)
class DescriptorUsage:
    open: int
    limit: int

    @property
    def ratio(self) -> float:
        return self.open / self.limit if self.limit > 0 else 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {"open": self.open, "limit": self.limit, "ratio": round(self.ratio, 3)}


def descriptor_usage() -> DescriptorUsage | None:
    """Open descriptors and the soft limit, or ``None`` where it cannot be read."""
    if resource is None:  # pragma: no cover
        return None
    for directory in _DESCRIPTOR_DIRS:
        try:
            # Listing the directory opens one descriptor of its own; it is
            # closed again before the count is used, so do not subtract it.
            count = len(os.listdir(directory))
        except OSError:
            continue
        soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft == resource.RLIM_INFINITY or soft <= 0:
            return None
        return DescriptorUsage(open=count, limit=int(soft))
    return None


class DescriptorWatch:
    """Warns once when usage crosses :data:`WARN_RATIO`, and again after recovery."""

    def __init__(self) -> None:
        self._warned = False

    def check(self) -> DescriptorUsage | None:
        usage = descriptor_usage()
        if usage is None:
            return None
        if usage.ratio >= WARN_RATIO and not self._warned:
            self._warned = True
            _LOGGER.warning(
                "%d of %d file descriptors are open (%.0f%%). Something is holding on "
                "to connections or files; at the limit the web interface stops "
                "accepting connections.",
                usage.open,
                usage.limit,
                usage.ratio * 100,
            )
        elif usage.ratio < WARN_RATIO / 2:
            self._warned = False
        return usage
