"""Condition matchers used by the categorisation engine.

The set is deliberately small and declarative so that rules can be created from
the UI, stored as JSON, and extended without touching Python code.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.common.domains import is_subdomain_of, normalize_domain

#: Operators a categorisation condition may use.
OPERATORS: tuple[str, ...] = (
    "suffix",      # domain is the value or a subdomain of it  (youtube.com)
    "equals",      # exact match
    "contains",    # substring anywhere                        (googlevideo)
    "startswith",
    "endswith",    # plain suffix on the string                (ytimg.com)
    "wildcard",    # shell-style glob                          (*.gstatic.com)
    "regex",
)

#: Operators that can be answered with a dictionary lookup.
INDEXED_OPERATORS: frozenset[str] = frozenset({"suffix", "equals"})

#: Fields a condition may inspect.
FIELDS: tuple[str, ...] = ("domain", "registrable")

_REGEX_CACHE: dict[str, re.Pattern[str] | None] = {}


def compile_regex(pattern: str) -> re.Pattern[str] | None:
    """Compile *pattern* case-insensitively, caching both hits and failures."""
    if pattern in _REGEX_CACHE:
        return _REGEX_CACHE[pattern]
    try:
        compiled: re.Pattern[str] | None = re.compile(pattern, re.IGNORECASE)
    except re.error:
        compiled = None
    if len(_REGEX_CACHE) > 512:
        _REGEX_CACHE.clear()
    _REGEX_CACHE[pattern] = compiled
    return compiled


def wildcard_to_regex(pattern: str) -> str:
    """Translate a glob such as ``*.gstatic.com`` into a regular expression."""
    parts = []
    for char in pattern:
        if char == "*":
            parts.append(".*")
        elif char == "?":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    return "^" + "".join(parts) + "$"


def match(operator: str, subject: str, value: str) -> bool:
    """Evaluate a single condition. Unknown operators never match."""
    if not subject or not value:
        return False

    if operator == "suffix":
        return is_subdomain_of(subject, value)
    if operator == "equals":
        return subject == normalize_domain(value)
    if operator == "contains":
        return value.lower() in subject
    if operator == "startswith":
        return subject.startswith(value.lower())
    if operator == "endswith":
        return subject.endswith(value.lower())
    if operator == "wildcard":
        compiled = compile_regex(wildcard_to_regex(value.lower()))
        return bool(compiled and compiled.match(subject))
    if operator == "regex":
        compiled = compile_regex(value)
        return bool(compiled and compiled.search(subject))
    return False


def matcher_for(operator: str, value: str) -> Callable[[str], bool]:
    """Return a closure for repeated evaluation of one condition."""

    def _match(subject: str) -> bool:
        return match(operator, subject, value)

    return _match
