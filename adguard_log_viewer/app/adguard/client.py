"""Thin async client for the AdGuard Home HTTP API.

Only the handful of endpoints the viewer needs are implemented. The client is
deliberately tolerant: AdGuard has changed field names across releases, so every
accessor falls back to the older spelling instead of raising.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.i18n import Message

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class AdGuardError(RuntimeError):
    """Raised when AdGuard Home cannot be reached or answers with an error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_auth_error(self) -> bool:
        return self.status_code in (401, 403)


class AdGuardClient:
    """Async AdGuard Home API client.

    ``username``/``password`` are sent as HTTP Basic auth. Depending on the
    AdGuard Home add-on configuration these are either Home Assistant
    credentials (the add-on's nginx validates them against the Supervisor
    ``/auth`` endpoint) or AdGuard Home's own users. See ARCHITECTURE.md §2.1.
    """

    def __init__(
        self,
        base_url: str,
        *,
        username: str = "",
        password: str = "",
        verify_ssl: bool = False,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        auth = httpx.BasicAuth(username, password) if username or password else None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=auth,
            verify=verify_ssl,
            timeout=timeout or DEFAULT_TIMEOUT,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AdGuardClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- plumbing -----------------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"/control{path}"
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as err:
            raise AdGuardError(
                Message(
                    "Cannot reach AdGuard Home at {url}: {error}",
                    url=self.base_url,
                    error=str(err),
                )
            ) from err

        if response.status_code >= 400:
            detail = _short_body(response)
            raise AdGuardError(
                Message(
                    "AdGuard Home returned HTTP {status} for {path}{detail}",
                    status=response.status_code,
                    path=path,
                    detail=detail,
                ),
                status_code=response.status_code,
            )

        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            # An HTML login page here means the request was intercepted by the
            # add-on's nginx auth layer rather than answered by AdGuard.
            raise AdGuardError(
                Message(
                    "AdGuard Home returned {content_type} instead of JSON for {path}; "
                    "check the credentials",
                    content_type=content_type or Message("an unknown content type"),
                    path=path,
                ),
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as err:
            raise AdGuardError(
                Message("Malformed JSON from AdGuard Home for {path}", path=path)
            ) from err

    # -- endpoints ----------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        """``GET /control/status`` — also the connectivity probe."""
        data = await self._get("/status")
        return data if isinstance(data, dict) else {}

    async def querylog(
        self,
        *,
        limit: int = 500,
        older_than: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """``GET /control/querylog``.

        AdGuard only pages *backwards*: ``older_than`` takes the timestamp of
        the oldest record already seen. There is no "newer than" parameter,
        which is why the ingest walks back from the newest page until it reaches
        its checkpoint.
        """
        params: dict[str, Any] = {"limit": max(1, min(limit, 5000))}
        if older_than:
            params["older_than"] = older_than
        if search:
            params["search"] = search
        data = await self._get("/querylog", params)
        if not isinstance(data, dict):
            return {"data": [], "oldest": ""}
        data.setdefault("data", [])
        data.setdefault("oldest", "")
        return data

    async def querylog_config(self) -> dict[str, Any]:
        """Query log settings; used to warn when logging is disabled."""
        try:
            data = await self._get("/querylog/config")
        except AdGuardError:
            data = await self._get("/querylog_info")  # pre-0.107.27 fallback
        return data if isinstance(data, dict) else {}

    async def clients(self) -> dict[str, Any]:
        """``GET /control/clients`` — persistent and runtime client names."""
        data = await self._get("/clients")
        return data if isinstance(data, dict) else {}

    async def client_names(self) -> dict[str, str]:
        """Flatten the clients endpoint into ``{ip: name}``."""
        try:
            payload = await self.clients()
        except AdGuardError as err:
            _LOGGER.debug("Could not read AdGuard clients: %s", err)
            return {}

        names: dict[str, str] = {}
        for entry in payload.get("clients") or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            for identifier in entry.get("ids") or []:
                identifier = str(identifier).strip()
                if name and identifier and "/" not in identifier:
                    names.setdefault(identifier, name)

        for entry in payload.get("auto_clients") or []:
            if not isinstance(entry, dict):
                continue
            ip = str(entry.get("ip") or "").strip()
            name = str(entry.get("name") or "").strip()
            if ip and name:
                names.setdefault(ip, name)

        return names


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


def _short_body(response: httpx.Response) -> str:
    """A one-line hint about the body, never raw markup.

    AdGuard sits behind nginx, and an nginx error page is several lines of HTML
    that used to be pasted straight into the add-on log. The page title carries
    the whole message.
    """
    try:
        text = response.text.strip()
    except Exception:  # pragma: no cover - defensive
        return ""
    if not text:
        return ""

    if "html" in response.headers.get("content-type", "").lower() or text.startswith("<"):
        title = _TITLE.search(text)
        summary = title.group(1) if title else _TAGS.sub(" ", text)
        summary = " ".join(summary.split())
        return f" ({summary[:100]})" if summary else " (an HTML error page)"

    return f": {' '.join(text.split())[:120]}"
