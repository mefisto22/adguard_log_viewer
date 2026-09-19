"""Runtime configuration.

Four layers, in order of precedence:

1. **environment variables** — used for development and for overriding a single
   value without touching the add-on options;
2. **the s6-overlay container environment** (``/run/s6/container_environment``),
   because s6 hands the process it launches a bare environment and keeps the
   real one there;
3. **the add-on options file** (``/data/options.json``), which Home Assistant
   writes from the add-on's Configuration tab;
4. **built-in defaults**.

Reading ``options.json`` here rather than through a ``bashio`` shell wrapper
keeps the container entry point a plain ``python -m app.main``, and makes the
whole mapping unit-testable.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

#: Gateway of the ``hassio`` docker bridge network. Add-ons reach the host — and
#: therefore every ``host_network: true`` add-on such as AdGuard Home — here.
HASSIO_HOST_GATEWAY = "172.30.32.1"

#: Base URL of the Supervisor REST API as seen from inside an add-on.
SUPERVISOR_API = "http://supervisor"

#: Where Home Assistant writes the add-on options.
DEFAULT_OPTIONS_FILE = "/data/options.json"

#: s6-overlay — which the Home Assistant base images use as their init — does
#: not pass the container environment to the process it launches. It stashes it
#: here instead, and expects programs to be started through ``with-contenv``.
#: The Dockerfile does exactly that, but reading the directory as well means the
#: add-on still sees SUPERVISOR_TOKEN and TZ if it is ever started another way.
#: Missing this cost the add-on its Supervisor token entirely: auto-discovery
#: could never reach the Supervisor, and every timestamp fell back to UTC.
DEFAULT_S6_ENVIRONMENT_DIR = "/run/s6/container_environment"

_options_cache: dict[str, Any] | None = None


def load_options(path: str | Path | None = None) -> dict[str, Any]:
    """Read the add-on options file. Missing or broken files yield ``{}``."""
    global _options_cache
    if path is None and _options_cache is not None:
        return _options_cache

    target = Path(path or os.environ.get("OPTIONS_FILE") or DEFAULT_OPTIONS_FILE)
    options: dict[str, Any] = {}
    try:
        with target.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            options = loaded
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not read the add-on options at %s: %s", target, err)

    if path is None:
        _options_cache = options
    return options


def container_environment(name: str) -> str | None:
    """Read one variable from the s6-overlay container environment."""
    directory = os.environ.get("S6_ENVIRONMENT_DIR") or DEFAULT_S6_ENVIRONMENT_DIR
    try:
        value = (Path(directory) / name).read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    # s6 writes the value verbatim, with at most a trailing newline.
    value = value.removesuffix("\n")
    return value or None


def _raw(env_name: str, option_name: str | None) -> Any:
    value = os.environ.get(env_name)
    if value is not None and value.strip() != "":
        return value.strip()

    stashed = container_environment(env_name)
    if stashed is not None and stashed.strip() != "":
        return stashed.strip()

    if option_name:
        option = load_options().get(option_name)
        if option is not None and option != "":
            return option
    return None


def _str(env_name: str, option_name: str | None = None, default: str = "") -> str:
    value = _raw(env_name, option_name)
    return default if value is None else str(value).strip()


def _int(
    env_name: str,
    option_name: str | None,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = _raw(env_name, option_name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _bool(env_name: str, option_name: str | None, default: bool) -> bool:
    raw = _raw(env_name, option_name)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable view of the process configuration."""

    # --- storage -----------------------------------------------------------
    data_dir: Path = field(default_factory=lambda: Path(_str("DATA_DIR", None, "/data")))
    db_filename: str = "adguard_log_viewer.db"

    # --- http server -------------------------------------------------------
    host: str = field(default_factory=lambda: _str("HOST", None, "0.0.0.0"))
    port: int = field(default_factory=lambda: _int("PORT", None, 8099, minimum=1, maximum=65535))

    # --- logging -----------------------------------------------------------
    log_level: str = field(default_factory=lambda: _str("LOG_LEVEL", "log_level", "info").lower())

    # --- query log source --------------------------------------------------
    #: ``auto`` | ``api`` | ``file``
    provider: str = field(default_factory=lambda: _str("PROVIDER", "provider", "auto").lower())
    adguard_url: str = field(default_factory=lambda: _str("ADGUARD_URL", "adguard_url"))
    adguard_username: str = field(
        default_factory=lambda: _str("ADGUARD_USERNAME", "adguard_username")
    )
    adguard_password: str = field(
        default_factory=lambda: _str("ADGUARD_PASSWORD", "adguard_password")
    )
    adguard_verify_ssl: bool = field(
        default_factory=lambda: _bool("ADGUARD_VERIFY_SSL", "adguard_verify_ssl", False)
    )
    adguard_slug: str = field(default_factory=lambda: _str("ADGUARD_SLUG", "adguard_slug"))
    querylog_path: str = field(default_factory=lambda: _str("QUERYLOG_PATH", "querylog_path"))

    # --- ingest ------------------------------------------------------------
    poll_interval: int = field(
        default_factory=lambda: _int("POLL_INTERVAL", "poll_interval", 10, minimum=2, maximum=3600)
    )
    ingest_batch_size: int = field(
        default_factory=lambda: _int(
            "INGEST_BATCH_SIZE", "ingest_batch_size", 500, minimum=50, maximum=5000
        )
    )
    max_pages_per_poll: int = field(
        default_factory=lambda: _int(
            "MAX_PAGES_PER_POLL", "max_pages_per_poll", 20, minimum=1, maximum=200
        )
    )
    ingest_enabled: bool = field(
        default_factory=lambda: _bool("INGEST_ENABLED", "ingest_enabled", True)
    )

    # --- retention ---------------------------------------------------------
    #: Days of history to keep. ``0`` means unlimited.
    retention_days: int = field(
        default_factory=lambda: _int(
            "RETENTION_DAYS", "retention_days", 30, minimum=0, maximum=3650
        )
    )
    cleanup_interval: int = field(
        default_factory=lambda: _int("CLEANUP_INTERVAL", None, 3600, minimum=60)
    )

    # --- presentation ------------------------------------------------------
    timezone: str = field(default_factory=lambda: _str("TZ", None, "UTC"))

    # --- supervisor --------------------------------------------------------
    supervisor_token: str = field(
        default_factory=lambda: _str("SUPERVISOR_TOKEN", None) or _str("HASSIO_TOKEN", None)
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def debug(self) -> bool:
        return self.log_level in {"debug", "trace"}

    @property
    def has_supervisor(self) -> bool:
        return bool(self.supervisor_token)

    def redacted(self) -> dict[str, object]:
        """Config snapshot safe to log or expose over the API.

        The password is reported only as "set" or "not set" — it is never
        returned by the API and never written to the log.
        """
        return {
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
            "log_level": self.log_level,
            "provider": self.provider,
            "adguard_url": self.adguard_url or "(auto-discover)",
            "adguard_username": self.adguard_username or "",
            "adguard_password_set": bool(self.adguard_password),
            "adguard_verify_ssl": self.adguard_verify_ssl,
            "querylog_path": self.querylog_path,
            "poll_interval": self.poll_interval,
            "ingest_batch_size": self.ingest_batch_size,
            "max_pages_per_poll": self.max_pages_per_poll,
            "ingest_enabled": self.ingest_enabled,
            "retention_days": self.retention_days,
            "timezone": self.timezone,
            "supervisor_available": self.has_supervisor,
        }


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings, building them on first use."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Drop the cached settings and options. Used by tests."""
    global _settings, _options_cache
    _settings = None
    _options_cache = None
