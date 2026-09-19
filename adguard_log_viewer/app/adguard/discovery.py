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
from app.i18n import Message, localize_all

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
#: The *host* port it is published on is whatever the user chose, and that is
#: what we are actually after — there is no sensible default for it, so nothing
#: here ever guesses one.
WEB_CONTAINER_PORT = "80/tcp"

#: Container ports that are never the web interface, whatever else is published.
NON_WEB_PORTS = frozenset({"53/tcp", "53/udp", "853/tcp", "784/udp", "8853/udp", "5443/tcp"})


@dataclass(slots=True)
class DiscoveredAdGuard:
    """Where AdGuard Home was found, and how we got there.

    ``url`` is ``None`` when the address could not be worked out. Earlier
    versions invented ``http://172.30.32.1:3000`` in that case, which sent
    people chasing a port that was never involved: AdGuard's *container* port
    is 80, and the *host* port is whatever they picked. Reporting nothing, plus
    the trace of what was actually looked at, is far more use than a guess.
    """

    url: str | None
    source: str
    slug: str = ""
    addon_name: str = ""
    version: str = ""
    confident: bool = True
    warnings: list[str] = field(default_factory=list)
    #: Human-readable record of every step, shown on the Settings page.
    steps: list[str] = field(default_factory=list)
    #: The port map the Supervisor reported, so a wrong guess is visible.
    ports: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return bool(self.url)

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "source": self.source,
            "slug": self.slug,
            "addon_name": self.addon_name,
            "version": self.version,
            "confident": self.confident,
            "resolved": self.resolved,
            "warnings": localize_all(list(self.warnings)),
            "steps": localize_all(list(self.steps)),
            "ports": dict(self.ports),
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


def normalize_url(value: str) -> str:
    """Accept the shorthands people actually type.

    ``9000`` and ``:9000`` mean "that port on the Home Assistant host";
    ``192.168.1.5:9000`` means that host; a full URL is left alone. Rejecting
    these outright would be pedantry — the port on its own is the only part
    most people have to think about.
    """
    text = value.strip().rstrip("/")
    if not text:
        return ""
    if "://" in text:
        return text
    if text.startswith(":"):
        text = text[1:]
    if text.isdigit():
        return f"http://{HASSIO_HOST_GATEWAY}:{text}"
    return f"http://{text}"


def _web_port(info: dict[str, Any]) -> tuple[int | None, str]:
    """The host port AdGuard's web interface is published on.

    Returns ``(port, explanation)``. The AdGuard add-on declares the interface
    on container port 80, but a fork or a different repository may not, so any
    single published TCP port that is not a DNS port is accepted as a fallback.
    """
    network = info.get("network")
    if not isinstance(network, dict):
        return None, Message("the Supervisor reported no port mapping for this add-on")

    value = network.get(WEB_CONTAINER_PORT)
    if isinstance(value, int) and value > 0:
        return value, Message(
            "{container_port} is published on host port {port}",
            container_port=WEB_CONTAINER_PORT,
            port=value,
        )

    published = {
        key: port
        for key, port in network.items()
        if key not in NON_WEB_PORTS
        and str(key).endswith("/tcp")
        and isinstance(port, int)
        and port > 0
    }
    if len(published) == 1:
        key, port = next(iter(published.items()))
        return port, Message(
            "{container_port} is the only published TCP port, using host port {port}",
            container_port=key,
            port=port,
        )
    if published:
        return None, Message(
            "several TCP ports are published ({ports}) and none of them is {container_port}",
            ports=", ".join(sorted(published)),
            container_port=WEB_CONTAINER_PORT,
        )

    return None, Message(
        "{container_port} has no host port assigned (the Supervisor reported {network})",
        container_port=WEB_CONTAINER_PORT,
        network=network or "{}",
    )


def _addon_host(info: dict[str, Any]) -> str:
    """Address at which this add-on can reach the AdGuard add-on.

    A ``host_network: true`` add-on — which AdGuard Home is — has no address of
    its own on the hassio bridge; the Supervisor reports the bridge gateway
    instead, and that is exactly where its host ports are reachable.
    """
    ip = str(info.get("ip_address") or "").strip()
    if ip and ip not in ("0.0.0.0", "None"):
        return ip
    return HASSIO_HOST_GATEWAY


def _build_from_info(info: dict[str, Any], source: str, steps: list[str]) -> DiscoveredAdGuard:
    port, explanation = _web_port(info)
    slug = str(info.get("slug") or "")
    name = str(info.get("name") or "")
    version = str(info.get("version") or "")
    raw_network = info.get("network")
    network: dict[str, Any] = raw_network if isinstance(raw_network, dict) else {}
    host = _addon_host(info)

    steps.append(
        Message(
            "'{name}' ({version}): {explanation}",
            name=name or slug,
            version=version or Message("unknown version"),
            explanation=explanation,
        )
    )

    result = DiscoveredAdGuard(
        url=f"http://{host}:{port}" if port else None,
        source=source,
        slug=slug,
        addon_name=name,
        version=version,
        steps=steps,
        ports=dict(network),
    )

    if port is None:
        result.confident = False
        result.warnings.append(
            Message(
                "The '{name}' add-on does not publish its web interface port, so its "
                "address cannot be worked out: {explanation}. Either open that add-on's "
                "Configuration page and assign a host port to {container_port} under "
                "Network, or set this add-on's 'AdGuard Home URL' option to the address "
                "you already use.",
                name=name or slug,
                explanation=explanation,
                container_port=WEB_CONTAINER_PORT,
            )
        )

    state = str(info.get("state") or "")
    if state not in ("started", ""):
        result.confident = False
        result.warnings.append(
            Message(
                "The '{name}' add-on is not running (state: {state}).",
                name=name or slug,
                state=state,
            )
        )

    return result


async def discover_adguard(
    *,
    supervisor_token: str,
    configured_url: str = "",
    configured_slug: str = "",
) -> DiscoveredAdGuard:
    """Resolve the AdGuard Home base URL. Never raises.

    When the address cannot be worked out, ``url`` comes back ``None`` and
    ``steps`` records what was looked at, so the Settings page can say why
    rather than reporting a failure against an address nobody configured.
    """
    steps: list[str] = []

    if configured_url:
        url = normalize_url(configured_url)
        steps.append(Message("Using the address from the add-on options: {url}", url=url))
        return DiscoveredAdGuard(url=url, source="configuration", steps=steps)

    supervisor = SupervisorClient(supervisor_token)
    if not supervisor.available:
        steps.append(Message("No Supervisor token, so the AdGuard add-on cannot be looked up."))
        return DiscoveredAdGuard(
            url=None,
            source="unavailable",
            confident=False,
            steps=steps,
            warnings=[
                Message(
                    "This add-on has no Supervisor token, so it cannot look the AdGuard "
                    "add-on up. Set the 'AdGuard Home URL' option explicitly."
                )
            ],
        )

    slugs: list[str] = []
    if configured_slug:
        slugs.append(configured_slug)
        steps.append(Message("Add-on slug from the options: {slug}", slug=configured_slug))

    services = await supervisor.discovery()
    for service in services:
        if str(service.get("service") or "").lower() == DISCOVERY_SERVICE:
            slug = str(service.get("addon") or "").strip()
            if slug and slug not in slugs:
                slugs.append(slug)
                steps.append(
                    Message("Supervisor discovery announced AdGuard as '{slug}'", slug=slug)
                )
    if not services:
        steps.append(
            Message("Supervisor discovery returned nothing; falling back to known slugs.")
        )

    announced = list(slugs)
    slugs.extend(slug for slug in CANDIDATE_SLUGS if slug not in slugs)

    probed: list[str] = []
    for slug in slugs:
        info = await supervisor.addon_info(slug)
        if not info:
            probed.append(slug)
            continue
        source = "supervisor-discovery" if slug in announced else "supervisor-slug-probe"
        if probed:
            steps.append(
                Message("No add-on installed under: {slugs}", slugs=", ".join(probed))
            )
            probed.clear()
        result = _build_from_info(info, source, steps)
        _LOGGER.info(
            "AdGuard Home add-on '%s' (%s): %s",
            result.addon_name or slug,
            result.version or "unknown version",
            result.url or "address could not be determined",
        )
        for warning in result.warnings:
            _LOGGER.warning("%s", warning)
        return result

    if probed:
        steps.append(Message("No add-on installed under: {slugs}", slugs=", ".join(probed)))
    return DiscoveredAdGuard(
        url=None,
        source="not-found",
        confident=False,
        steps=steps,
        warnings=[
            Message(
                "No AdGuard Home add-on was found through the Supervisor. Set the "
                "'AdGuard Home URL' option to the address you use to open AdGuard."
            )
        ],
    )
