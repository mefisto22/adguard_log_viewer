"""Runtime settings.

Two layers, kept deliberately distinct:

* **Add-on options** (connection details, poll interval, log level, timezone)
  are owned by Home Assistant. They arrive as environment variables and are
  read-only here — the Settings page shows them and says where to change them.
* **Application settings** (UI preferences, a retention override, whether ingest
  runs) live in the database and can be changed from the Settings page while the
  add-on is running.

Where both can express the same thing — retention — the stored override wins
when it is set, and the add-on option is the default. That is the only overlap,
and it is spelled out in the API response.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from app.config import Settings
from app.db.sqlutil import kv_all, kv_delete, kv_set

#: Keys the API will accept, with a validator for each.
EDITABLE: dict[str, str] = {
    "ui.theme": "theme",
    "ui.default_range": "str",
    "ui.page_size": "page_size",
    "ui.columns": "list",
    "ui.density": "density",
    "ui.live_updates": "bool",
    "retention_days": "retention",
    "ingest.enabled": "bool",
}

DEFAULTS: dict[str, Any] = {
    "ui.theme": "system",
    "ui.default_range": "24h",
    "ui.page_size": 100,
    "ui.columns": [],
    "ui.density": "comfortable",
    "ui.live_updates": True,
    "ingest.enabled": True,
}

THEMES = ("system", "light", "dark")
DENSITIES = ("compact", "comfortable")

#: Retention choices offered by the UI. ``0`` keeps everything.
RETENTION_CHOICES: tuple[int, ...] = (1, 7, 30, 90, 180, 365, 0)


class SettingsError(ValueError):
    """A settings value was rejected."""


def _validate(key: str, value: Any) -> Any:
    kind = EDITABLE.get(key)
    if kind is None:
        raise SettingsError(f"{key!r} is not a settable option")

    if kind == "theme":
        if value not in THEMES:
            raise SettingsError(f"theme must be one of {', '.join(THEMES)}")
        return value
    if kind == "density":
        if value not in DENSITIES:
            raise SettingsError(f"density must be one of {', '.join(DENSITIES)}")
        return value
    if kind == "page_size":
        try:
            number = int(value)
        except (TypeError, ValueError) as err:
            raise SettingsError("page_size must be a number") from err
        return max(25, min(number, 500))
    if kind == "retention":
        if value is None:
            return None
        try:
            number = int(value)
        except (TypeError, ValueError) as err:
            raise SettingsError("retention_days must be a number") from err
        if number < 0:
            raise SettingsError("retention_days cannot be negative")
        return number
    if kind == "bool":
        return bool(value)
    if kind == "list":
        if not isinstance(value, list):
            raise SettingsError(f"{key} must be a list")
        return [str(item) for item in value][:64]
    return str(value)


def stored(conn: sqlite3.Connection) -> dict[str, Any]:
    """Only the keys the user may edit, with defaults filled in."""
    raw = kv_all(conn, "settings")
    result = dict(DEFAULTS)
    for key in EDITABLE:
        if key in raw:
            result[key] = raw[key]
    return result


def update(conn: sqlite3.Connection, values: dict[str, Any]) -> dict[str, Any]:
    for key, value in values.items():
        validated = _validate(key, value)
        if validated is None:
            kv_delete(conn, "settings", key)
        else:
            kv_set(conn, "settings", key, validated)
    return stored(conn)


def effective_retention_days(conn: sqlite3.Connection, settings: Settings) -> int:
    override = kv_all(conn, "settings").get("retention_days")
    if isinstance(override, int) and override >= 0:
        return override
    return settings.retention_days


def ingest_enabled(conn: sqlite3.Connection, settings: Settings) -> bool:
    if not settings.ingest_enabled:
        return False
    value = kv_all(conn, "settings").get("ingest.enabled")
    return True if value is None else bool(value)


def describe(conn: sqlite3.Connection, settings: Settings) -> dict[str, Any]:
    """The whole settings picture, for the Settings page."""
    return {
        "app": stored(conn),
        "addon_options": settings.redacted(),
        "effective": {
            "retention_days": effective_retention_days(conn, settings),
            "ingest_enabled": ingest_enabled(conn, settings),
            "poll_interval": settings.poll_interval,
            "timezone": settings.timezone,
        },
        "choices": {
            "themes": list(THEMES),
            "densities": list(DENSITIES),
            "retention_days": list(RETENTION_CHOICES),
        },
        "editable_keys": sorted(EDITABLE),
    }
