# Changelog

## 0.1.0

First release.

- Reads the AdGuard Home query log through its HTTP API, with the AdGuard
  add-on's address and port discovered through the Supervisor at runtime.
- Incremental ingest with deduplication, plus a bounded historic backfill.
- SQLite storage with schema migrations, indexes and a per-minute activity
  rollup.
- Log viewer with multi-term ANY/ALL search, a nested AND/OR filter builder and
  saved filters.
- Automatic domain categorisation from a bundled, extensible rule set, plus your
  own rules and manual tags.
- Devices, people and IP aliases, so the log can be filtered by who rather than
  by address.
- Dashboard, plus detail pages for domains, devices and people.
- Configurable retention with automatic cleanup.
- Light and dark themes, served through Home Assistant ingress.
