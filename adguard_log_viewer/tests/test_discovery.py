"""Finding the AdGuard Home add-on, and saying so when it cannot be found.

The original version invented ``http://172.30.32.1:3000`` whenever the lookup
came up short. AdGuard's *container* port is 80 and the *host* port is whatever
the user picked, so 3000 was never more than a guess — and it turned every
failure into "cannot reach AdGuard at :3000", which points at the wrong thing.
These tests pin the behaviour that replaced it: resolve it properly, or return
nothing and explain what was looked at.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.adguard import discovery
from app.adguard.discovery import DiscoveredAdGuard, discover_adguard, normalize_url


def adguard_info(
    *,
    ports: dict[str, Any] | None = None,
    slug: str = "a0d7b954_adguard",
    state: str = "started",
    ip: str = "172.30.32.1",
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "slug": slug,
        "name": "AdGuard Home",
        "version": "7.1.0",
        "ip_address": ip,
        "state": state,
        "host_network": True,
    }
    if ports is not None:
        info["network"] = ports
    return info


@pytest.fixture
def supervisor(monkeypatch: pytest.MonkeyPatch):
    """Stub the Supervisor REST calls."""
    routes: dict[str, Any] = {}

    async def fake_get(self: Any, path: str) -> Any:
        return routes.get(path)

    monkeypatch.setattr(discovery.SupervisorClient, "get", fake_get)
    return routes


async def discover(**kwargs: Any) -> DiscoveredAdGuard:
    return await discover_adguard(supervisor_token="token", **kwargs)


class TestNormalizeUrl:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("9000", "http://172.30.32.1:9000"),
            (":9000", "http://172.30.32.1:9000"),
            ("  9000  ", "http://172.30.32.1:9000"),
            ("192.168.1.5:9000", "http://192.168.1.5:9000"),
            ("adguard.local", "http://adguard.local"),
            ("http://10.0.0.1:80/", "http://10.0.0.1:80"),
            ("https://adguard.example/", "https://adguard.example"),
            ("", ""),
        ],
    )
    def test_shorthands(self, given: str, expected: str) -> None:
        assert normalize_url(given) == expected


class TestPortDiscovery:
    @pytest.mark.anyio
    async def test_finds_whatever_host_port_the_user_chose(self, supervisor: dict) -> None:
        """The host port is the user's choice; nothing may assume 80 or 3000."""
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(
            ports={"53/udp": 53, "80/tcp": 9876}
        )
        result = await discover()
        assert result.url == "http://172.30.32.1:9876"
        assert result.resolved is True
        assert result.warnings == []

    @pytest.mark.anyio
    async def test_unpublished_port_yields_no_url_and_an_explanation(
        self, supervisor: dict
    ) -> None:
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(
            ports={"53/udp": 53, "80/tcp": None}
        )
        result = await discover()
        assert result.url is None
        assert result.resolved is False
        assert "does not publish its web interface port" in result.warnings[0]
        # The reported port map is what makes this diagnosable.
        assert result.ports == {"53/udp": 53, "80/tcp": None}

    @pytest.mark.anyio
    async def test_no_port_map_at_all(self, supervisor: dict) -> None:
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info()
        result = await discover()
        assert result.url is None
        assert any("no port mapping" in step for step in result.steps)

    @pytest.mark.anyio
    async def test_a_single_other_tcp_port_is_accepted(self, supervisor: dict) -> None:
        """Covers a fork that declares its interface on a different port."""
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(
            ports={"53/udp": 53, "53/tcp": 53, "3000/tcp": 3000}
        )
        result = await discover()
        assert result.url == "http://172.30.32.1:3000"

    @pytest.mark.anyio
    async def test_ambiguous_ports_are_not_guessed(self, supervisor: dict) -> None:
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(
            ports={"8080/tcp": 8080, "9090/tcp": 9090}
        )
        result = await discover()
        assert result.url is None
        assert any("several TCP ports" in step for step in result.steps)

    @pytest.mark.anyio
    async def test_dns_ports_are_never_mistaken_for_the_web_interface(
        self, supervisor: dict
    ) -> None:
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(
            ports={"53/tcp": 53, "853/tcp": 853, "80/tcp": None}
        )
        result = await discover()
        assert result.url is None


class TestSlugResolution:
    @pytest.mark.anyio
    async def test_uses_the_slug_the_supervisor_announces(self, supervisor: dict) -> None:
        supervisor["/discovery"] = {
            "discovery": [{"service": "adguard", "addon": "custom_adguard"}]
        }
        supervisor["/addons/custom_adguard/info"] = adguard_info(
            slug="custom_adguard", ports={"80/tcp": 7000}
        )
        result = await discover()
        assert result.slug == "custom_adguard"
        assert result.url == "http://172.30.32.1:7000"
        assert result.source == "supervisor-discovery"

    @pytest.mark.anyio
    async def test_falls_back_to_known_slugs(self, supervisor: dict) -> None:
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(ports={"80/tcp": 8000})
        result = await discover()
        assert result.source == "supervisor-slug-probe"
        assert result.url == "http://172.30.32.1:8000"

    @pytest.mark.anyio
    async def test_an_explicit_slug_wins(self, supervisor: dict) -> None:
        supervisor["/addons/my_adguard/info"] = adguard_info(
            slug="my_adguard", ports={"80/tcp": 4242}
        )
        result = await discover(configured_slug="my_adguard")
        assert result.url == "http://172.30.32.1:4242"

    @pytest.mark.anyio
    async def test_nothing_installed(self, supervisor: dict) -> None:
        result = await discover()
        assert result.url is None
        assert result.source == "not-found"
        assert "No AdGuard Home add-on was found" in result.warnings[0]


class TestConfiguredUrl:
    @pytest.mark.anyio
    async def test_the_configured_address_wins_and_is_normalised(
        self, supervisor: dict
    ) -> None:
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(ports={"80/tcp": 1111})
        result = await discover(configured_url="9876")
        assert result.url == "http://172.30.32.1:9876"
        assert result.source == "configuration"

    @pytest.mark.anyio
    async def test_no_supervisor_token_says_so(self) -> None:
        result = await discover_adguard(supervisor_token="")
        assert result.url is None
        assert "no Supervisor token" in result.warnings[0]


class TestState:
    @pytest.mark.anyio
    async def test_a_stopped_addon_is_flagged_but_still_resolved(
        self, supervisor: dict
    ) -> None:
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(
            ports={"80/tcp": 9000}, state="stopped"
        )
        result = await discover()
        assert result.url == "http://172.30.32.1:9000"
        assert result.confident is False
        assert any("not running" in warning for warning in result.warnings)


class TestNoInventedFallback:
    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "ports", [None, {"80/tcp": None}, {"53/udp": 53}, {"a": 1, "b": 2}]
    )
    async def test_port_3000_is_never_invented(self, supervisor: dict, ports: Any) -> None:
        supervisor["/addons/a0d7b954_adguard/info"] = adguard_info(ports=ports)
        result = await discover()
        assert result.url is None, f"invented an address for ports={ports}"

    def test_the_module_holds_no_default_port(self) -> None:
        assert not hasattr(discovery, "FALLBACK_PORT")
