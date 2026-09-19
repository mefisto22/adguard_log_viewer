"""AdGuard Home access: HTTP client and Home Assistant based discovery."""

from app.adguard.client import AdGuardClient, AdGuardError
from app.adguard.discovery import DiscoveredAdGuard, discover_adguard

__all__ = ["AdGuardClient", "AdGuardError", "DiscoveredAdGuard", "discover_adguard"]
