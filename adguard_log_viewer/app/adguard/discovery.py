"""Locate the AdGuard Home add-on at runtime.

Nothing about AdGuard's installation is hardcoded into the rest of the
application. The slug, the IP address and the port are all resolved through the
Supervisor API, so the viewer keeps working after an AdGuard update, a
reinstall, or an install from a different repository.

Resolution order (see ARCHITECTURE.md §3):

1. an explicit ``adguard_url`` from the add-on options;
2. ``GET /discovery`` — AdGuard announces itself, which gives us its slug;
3. ``GET /addons/<slug>/info`` — gives ``ip_address`` and the published ports;
4. the same info call against a small list of well-known slugs;
5. the hassio bridge gateway on AdGuard's default web port.

Steps 2 and 3 are both reachable with ``hassio_role: default``: ``/discovery``
is on the Supervisor's api_bypass list and ``/addons/<slug>/info`` matches the
``^/.+/info$`` pattern granted to the default role.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import HASSIO_HOST_GATEWAY, SUPERVISOR_API

_LOGGER = logging.getLogger(__name__)

#: Discovery service name announced by the AdGuard Home add-on.
DISCOVERY_SERVICE = "adguard"

#: Fallback slugs, tried only when discovery returns nothing. Not authoritative:
#: the slug is normally learned at runtime.
CANDIDATE_SLUGS: tuple[str, ...] = (
    "a0d7b954_adguard",
    "adguard",
    "core_adguard",
    "local_adguard",
)

#: The container port the AdGuard add-on's "direct" web interface listens on.
WEB_CONTAINER_PORT = "80/tcp"

#: Used only when every discovery step failed.
FALLBACK_PORT = 3000


@dataclass(slots=True)
class DiscoveredAdGuard:
    """Where AdGuard Home was found, and how we got there."""

    url: str
    source: str
    slug: str = ""
    addon_name: str = ""
    version: str = ""
    confident: bool = True
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "source": self.source,
            "slug": self.slug,
            "addon_name": self.addon_name,
            "version": self.version,
            "confident": self.confident,
            "warnings": list(self.warnings),
        }


class SupervisorClient:
    """Minimal Supervisor REST client."""

    def __init__(self, token: str, *, base_url: str = SUPERVISOR_API) -> None:
        self._token = token
        self._base_url = base_url

    @property
    def available(self) -> bool:
        return bool(self._token)

    async def get(self, path: str) -> dict[str, Any] | None:
        if not self.available:
            return None
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as err:
            _LOGGER.debug("Supervisor request %s failed: %s", path, err)
            return None

        if response.status_code != 200:
            _LOGGER.debug("Supervisor %s returned HTTP %s", path, response.status_code)
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    async def discovery(self) -> list[dict[str, Any]]:
        data = await self.get("/discovery")
        if not data:
            return []
        services = data.get("discovery")
        return [item for item in services or [] if isinstance(item, dict)]

    async def addon_info(self, slug: str) -> dict[str, Any] | None:
        return await self.get(f"/addons/{slug}/info")


def _web_port(info: dict[str, Any]) -> int | None:
    """Host port bound to AdGuard's web interface, if the user published one."""
    network = info.get("network")
    if not isinstance(network, dict):
        return None
    for key in (WEB_CONTAINER_PORT, "80", "3000/tcp", "3000"):
        value = network.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _addon_host(info: dict[str, Any]) -> str:
    """Address at which this add-on can reach the AdGuard add-on.

    A ``host_network: true`` add-on — which AdGuard Home is — has no address of
    its own on the hassio bridge; the Supervisor reports the bridge gateway
    instead, and that is exactly where its host ports are reachable.
    """
    ip = str(info.get("ip_address") or "").strip()
    if ip and ip != "0.0.0.0":
        return ip
    return HASSIO_HOST_GATEWAY


def _build_from_info(info: dict[str, Any], source: str) -> DiscoveredAdGuard | None:
    port = _web_port(info)
    slug = str(info.get("slug") or "")
    name = str(info.get("name") or "")
    version = str(info.get("version") or "")

    if port is None:
        warning = (
            f"The '{name or slug}' add-on has no host port assigned to its web interface "
            f"({WEB_CONTAINER_PORT}). Open the AdGuard Home add-on's Configuration page, "
            f"set a port under Network, and restart it."
        )
        return DiscoveredAdGuard(
            url=f"http://{_addon_host(info)}:{FALLBACK_PORT}",
            source=source,
            slug=slug,
            addon_name=name,
            version=version,
            confident=False,
            warnings=[warning],
        )

    return DiscoveredAdGuard(
        url=f"http://{_addon_host(info)}:{port}",
        source=source,
        slug=slug,
        addon_name=name,
        version=version,
    )


async def discover_adguard(
    *,
    supervisor_token: str,
    configured_url: str = "",
    configured_slug: str = "",
) -> DiscoveredAdGuard:
    """Resolve the AdGuard Home base URL. Never raises."""
    if configured_url:
        return DiscoveredAdGuard(url=configured_url.rstrip("/"), source="configuration")

    supervisor = SupervisorClient(supervisor_token)
    if not supervisor.available:
        return DiscoveredAdGuard(
            url=f"http://{HASSIO_HOST_GATEWAY}:{FALLBACK_PORT}",
            source="fallback",
            confident=False,
            warnings=[
                "No Supervisor token available, so the AdGuard add-on could not be "
                "discovered. Set the AdGuard URL explicitly in the add-on options."
            ],
        )

    slugs: list[str] = []
    if configured_slug:
        slugs.append(configured_slug)

    for service in await supervisor.discovery():
        if str(service.get("service") or "").lower() == DISCOVERY_SERVICE:
            slug = str(service.get("addon") or "").strip()
            if slug and slug not in slugs:
                slugs.append(slug)

    discovered_slugs = list(slugs)
    slugs.extend(slug for slug in CANDIDATE_SLUGS if slug not in slugs)

    for slug in slugs:
        info = await supervisor.addon_info(slug)
        if not info:
            continue
        source = "supervisor-discovery" if slug in discovered_slugs else "supervisor-slug-probe"
        result = _build_from_info(info, source)
        if result is None:
            continue
        if str(info.get("state") or "") not in ("started", ""):
            result.warnings.append(
                f"The '{result.addon_name or slug}' add-on is not running "
                f"(state: {info.get('state')})."
            )
            result.confident = False
        _LOGGER.info(
            "Discovered AdGuard Home add-on '%s' (%s) at %s via %s",
            result.addon_name or slug,
            result.version or "unknown version",
            result.url,
            source,
        )
        return result

    return DiscoveredAdGuard(
        url=f"http://{HASSIO_HOST_GATEWAY}:{FALLBACK_PORT}",
        source="fallback",
        confident=False,
        warnings=[
            "The AdGuard Home add-on could not be found through the Supervisor. "
            "Set the AdGuard URL explicitly in the add-on options."
        ],
    )
