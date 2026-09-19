# AdGuard Log Viewer

**English** · [Magyar](#magyar)

A DNS query log viewer and analyzer for [AdGuard Home][adguard], packaged as a
**Home Assistant OS add-on**.

Not a text log viewer: it makes DNS traffic searchable along devices, people,
categories and your own tags, and stays fast across millions of records.

The interface follows Home Assistant's language — Hungarian and English are both
supported, in the add-on's configuration page and in the web interface alike.

---

## Contents

- [What it does](#what-it-does)
- [Language](#language)
- [Architecture](#architecture)
- [Home Assistant OS compatibility](#home-assistant-os-compatibility)
- [AdGuard integration](#adguard-integration)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running it for development](#running-it-for-development)
- [Building](#building)
- [Tests](#tests)
- [Database](#database)
- [Backups](#backups)
- [Upgrading](#upgrading)
- [Project layout](#project-layout)
- [Performance](#performance)
- [Privacy](#privacy)

---

## What it does

**Log view**

- A virtualised table with per-column visibility — fast at hundreds of thousands of rows.
- Every record carries: timestamp, client IP, device name, person, domain, query
  type (A / AAAA / CNAME / PTR / HTTPS / SVCB / …), answer, DNS status, blocked
  or allowed, the AdGuard rule and filter list, response time, upstream,
  protocol, and the categories and tags the application assigns.
- Near real-time updates over Server-Sent Events, with an automatic polling
  fallback. Only the delta is fetched, never the whole log.

**Search and filtering**

- Several search terms at once, in **ANY (OR)** and **ALL (AND)** mode.
- A visual filter builder for arbitrarily deep `(A OR B) AND (C OR D)` trees.
- Fields: domain, registrable domain, client IP, device name, person, tag,
  category, query type, blocked, DNS status, AdGuard reason, rule, filter list
  ID, upstream, answer, response time, timestamp.
- Operators: equals, not equals, contains, not contains, starts with, ends with,
  regex, not regex, in list, not in list, >, ≥, <, ≤, is empty.
- Saved filters: create, edit, rename, delete, apply in one click.

**Categorisation**

- 96 built-in rules covering 89 tags and categories (Google, YouTube, Meta,
  streaming, advertising, tracking, telemetry, AI, IoT, gaming, banking, news, …).
- Your own rules: suffix, exact, contains, starts/ends with, wildcard, regex; in
  ANY or ALL mode, with a priority and a built-in tester.
- Manual per-domain tags, which automatic re-classification never overwrites.

**Devices and people**

- IP → your own name, overriding the name AdGuard reports.
- Several devices to one person; filtering on one or several people at once.
- The Devices page: IP, AdGuard name, your name, person, first and last activity,
  query count, top domains and categories.

**Dashboard and detail pages**

- Daily / hourly / custom periods, a query timeline, the blocked share, top
  domains, blocked domains, devices, people, categories, tags, query types and
  upstream servers.
- Domain, device and person detail pages, each with its own timeline and breakdowns.

---

## Language

The add-on speaks **English and Hungarian**, and follows Home Assistant:

* **The add-on's Configuration page.** Home Assistant renders it from
  `translations/en.yaml` and `translations/hu.yaml` and picks the file matching
  the user's own language — nothing to configure.
* **The web interface.** Under ingress the page is served from the same origin as
  Home Assistant, so the app reads the `lang` attribute of the Home Assistant
  document around it. That reflects the language chosen in the user's profile,
  not just the system default. Opened outside Home Assistant it falls back to the
  browser's language, and then to English.
* **Messages from the backend** — validation errors, and the diagnostics about
  reaching AdGuard Home — travel in the same language: each request carries an
  `Accept-Language` header and the reply is translated to match.
* **Dates, numbers and relative times** follow the same language, so a Hungarian
  page does not mix Hungarian labels with `09/19/2026` timestamps.

Settings → Appearance → Language overrides all of this per user, with
*Follow Home Assistant*, *English* and *Magyar*.

Adding a third language means adding `frontend/src/i18n/<code>.ts`, a section in
`app/i18n.py` and a `translations/<code>.yaml`. The dictionaries are typed
against English, so a missing key is a compile error rather than a blank label;
the backend catalogue is checked the same way by `tests/test_i18n.py`.

---

## Architecture

The full reasoning — including the source-level verification of the Home
Assistant OS limits — is in [`ARCHITECTURE.md`](ARCHITECTURE.md). In short:

```
AdGuard Home add-on            this add-on
┌─────────────────┐            ┌──────────────────────────────────────┐
│ AdGuardHome     │            │ ingest loop                          │
│  127.0.0.1:45158│◀──nginx────│   AdGuardApiQueryLogProvider  ──┐    │
│                 │  :80/tcp   │   AdGuardFileQueryLogProvider ──┤    │
└─────────────────┘            │                                 ▼    │
         ▲                     │                       normalisation  │
         │ Supervisor API      │                          + dedup     │
         │ discovery           │                             ▼        │
┌─────────────────┐            │  SQLite (WAL)  ◀── categorisation     │
│ Supervisor      │◀───────────│     ▲                                │
└─────────────────┘            │     │ SQL filtering / aggregation    │
                               │  FastAPI  ──ingress──▶ React UI      │
                               └──────────────────────────────────────┘
```

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.13 + FastAPI + uvicorn | A small image on Home Assistant's own Alpine base-python image; every dependency has a `musllinux` wheel for aarch64 **and** x86_64, so the build compiles nothing. |
| Database | SQLite (WAL), stdlib `sqlite3` | One file, no extra service, easy to back up. Under WAL the writing ingest and the reading API run side by side. |
| Frontend | React 19 + TypeScript + Vite | A static build served by the backend — no second process to run. |
| Routing | hash routing | The ingress prefix is generated per session; with hash routing it never has to be injected into the frontend. |
| Realtime | SSE with a polling fallback | One-way, proxy-friendly and simpler than a WebSocket. |

---

## Home Assistant OS compatibility

The **host-side** location of the AdGuard query log under HA OS is:

```
/mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/data/querylog.json
```

**That path is not reachable from another add-on**, and there is no supported way
around it:

| Route | Works? | Why not |
|---|---|---|
| Reading the file directly | ❌ | The `map:` key only knows the `homeassistant_config`, `addon_config`, `all_addon_configs`, `ssl`, `addons`, `backup`, `share`, `media` and `data` types — none of them is another add-on's `/data`. |
| File access through the Supervisor API | ❌ | No such endpoint exists. |
| The Supervisor ingress proxy | ❌ | It requires an `ingress_session` cookie that only HA Core can mint, because of `@require_home_assistant`. |
| AdGuard's ingress nginx | ❌ | `allow 172.30.32.2; deny all;` — the Supervisor only. |
| AdGuard's API directly (`:45158`) | ❌ | `--host 127.0.0.1`, which is the **host's** loopback. |
| Backup / export, then unpack | ⚠️ | Technically possible, but nowhere near real time and heavy on I/O. Rejected. |
| **AdGuard's "direct" web port + HTTP API** | ✅ | The one supported, stable route. |

So the add-on uses **AdGuard Home's HTTP API**. The price is a one-time change on
the AdGuard add-on: assign a host port to the *Web interface* port (`80/tcp`).
The steps are in section 2 of [`DOCS.md`](adguard_log_viewer/DOCS.md).

The `file` provider stays for Supervised / Container / Docker setups and for
development, but it is not what runs under HA OS, and the Settings page says so
when the configured file cannot be read.

---

## AdGuard integration

* **Nothing is hardcoded.** The `a0d7b954_adguard` slug is only a fallback
  candidate; the real slug, IP and port are resolved at runtime:
  `GET /discovery` → the AdGuard slug → `GET /addons/<slug>/info` → `ip_address`
  + `network["80/tcp"]`. Both endpoints are reachable with the least privilege
  (`hassio_role: default`).
* **No port is guessed.** `80/tcp` is AdGuard's container-side port; the host
  port is the user's choice. When it cannot be resolved the add-on does not
  invent an address — the Settings page shows, step by step, what it looked at —
  and the `adguard_url` option accepts a bare port number.
* The add-on **never modifies** the AdGuard add-on's files, configuration or
  container, and uses only AdGuard's **versioned HTTP API**, not its internal
  file format, so an AdGuard update does not break it.
* The data source sits behind the `QueryLogProvider` abstraction
  (`AdGuardApiQueryLogProvider`, `AdGuardFileQueryLogProvider`); the rest of the
  application does not know where records come from.

---

## Installation

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories** → add this
   repository's URL.
2. Install the **AdGuard Log Viewer** add-on.
3. Do the [one-time AdGuard setup](adguard_log_viewer/DOCS.md#2-one-time-adguard-setup--skip-this-and-nothing-will-work).
4. Enter a Home Assistant username and password on the add-on's
   **Configuration** tab.
5. Start it, and open it from the sidebar.

## Configuration

The full option list is in [`DOCS.md`](adguard_log_viewer/DOCS.md#4-options).
There are two levels:

* **Add-on options** (connection, poll interval, retention, log level) — Home
  Assistant owns these, and they need a restart.
* **Application settings** (language, theme, density, default period, page size,
  retention override, ingest on/off) — on the Settings page, effective
  immediately.

Options are read straight from `/data/options.json` (`app/config.py`); there is
no bashio shell layer. The order is: environment variable → the s6 container
environment → add-on option → default.

---

## Running it for development

You need Python 3.11+ and Node 20+.

```bash
# backend
cd adguard_log_viewer
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
DATA_DIR=./dev-data INGEST_ENABLED=false .venv/bin/python -m app.main
```

```bash
# frontend (a second terminal) — proxies /api calls to 8099
cd frontend
npm install
npm run dev
```

The backend listens on `http://127.0.0.1:8099` and the Vite dev server on
`http://127.0.0.1:5173`.

Without a real AdGuard the Settings page reports that the provider is
unreachable, but the interface is usable. To generate synthetic data, see
`tools/benchmark.py`.

---

## Building

The frontend build lands in the backend's `app/static` directory and **is
committed to the repository** — so the Supervisor only installs Python on the HA
device and never has to run Node on a Raspberry Pi.

```bash
cd frontend
npm run build          # → adguard_log_viewer/app/static
```

The Docker image (multi-arch):

```bash
cd adguard_log_viewer
docker build --build-arg BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21 -t aglv:aarch64 .
docker build --platform linux/amd64 --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21 -t aglv:amd64 .
```

Thanks to `pip install --only-binary :all:` a missing wheel is a loud build
failure rather than a silent source build. Availability can be checked up front:

```bash
cd adguard_log_viewer
.venv/bin/python tools/check_wheels.py
```

---

## Tests

```bash
cd adguard_log_viewer
.venv/bin/python -m pytest -q          # 368 tests
.venv/bin/ruff check app tests tools
.venv/bin/mypy app
```

```bash
cd frontend
npm run typecheck
npm run lint
npm test
```

What is covered: the AdGuard API and file parsers (including decoding the
base64 DNS wire format), deduplication, checkpoint and backfill logic, the filter
engine (parsing, AND/OR/NOT, every operator, SQL injection), domain matching,
regex, tag and category rules, IP → device and device → person assignment,
retention cleanup, the configuration layers, the whole HTTP API, the security
limits (SQL injection on every text field, path traversal in the static handler,
the query time limit, regex length), **translation** (that every message the
backend can produce has a Hungarian entry, and that the two frontend
dictionaries agree on keys and placeholders), and **packaging**: that the
built-in rule set is under version control, that `config.yaml` passes the
Supervisor's constraints, that the option translations match the schema, and
that the compiled frontend is present.

The packaging tests exist because two faults only showed up on install: an
unanchored `data/` pattern in `.gitignore` excluded the built-in rule file from
the repository (everything was green locally, 18 tests failed in CI), and an
`image: null` key made `config.yaml` invalid, which kept the add-on from
appearing in the Add-on Store at all.

Benchmarking on synthetic data:

```bash
cd adguard_log_viewer
.venv/bin/python tools/benchmark.py --records 1000000
```

---

## Database

SQLite in WAL mode, in the add-on's `/data` directory:
`/data/adguard_log_viewer.db`.

```
persons ── clients ── queries ── domains ── domain_tags ── tags
                                    │
rules   saved_filters   settings   ingest_state   stats_minute
```

Schema migrations live in `app/db/migrations.py` as an append-only list keyed off
`PRAGMA user_version`. A released migration is never edited, only followed by a
new one, so an upgrade loses no data.

**Deduplication.** AdGuard has no record identifier of its own, so every record
gets a stable 64-bit `uid` from `blake2b(ts_ns | client | domain | qtype)`, with
a `UNIQUE` index over it. The checkpoint is only an optimisation; correctness
comes from the index, so neither a restart, an overlapping API page nor a log
rotation can duplicate anything.

---

## Backups

The database sits in the add-on's `/data` directory, which **Home Assistant's
backup takes automatically**. With a large database that noticeably grows the
backup — lower `retention_days` if it does.

A manual copy on the host:

```bash
ha addons stop adguard_log_viewer
# copy /mnt/data/supervisor/apps/data/<slug>/adguard_log_viewer.db
ha addons start adguard_log_viewer
```

## Upgrading

The schema migrates automatically when the add-on is updated. Imported records,
device names, people, tags, rules and saved filters are all kept. Updating
AdGuard Home does not affect the add-on, because only the versioned HTTP API is
used.

---

## Project layout

```
.
├── ARCHITECTURE.md                 the architecture and the HA OS limits
├── repository.yaml                 Home Assistant add-on repository descriptor
├── .github/workflows/ci.yaml       lint, type check, tests, wheel and image build
├── frontend/                       React + TypeScript source (development only)
│   └── src/
│       ├── api/                    HTTP client and endpoints
│       ├── components/             FilterBar, FilterBuilder, QueryTable, chart, UI
│       ├── i18n/                   English and Hungarian dictionaries
│       ├── pages/                  Dashboard, Log, Devices, People, Domains, Rules, …
│       ├── stores/                 app and filter state (zustand)
│       ├── hooks/                  data fetching, live updates over SSE
│       ├── types/                  the backend API's types
│       └── utils/                  formatting
└── adguard_log_viewer/             the add-on (the Supervisor's build context)
    ├── config.yaml  build.yaml  Dockerfile  DOCS.md  translations/
    ├── tests/                      pytest tests
    ├── tools/                      benchmark, rule generator, wheel check
    └── app/
        ├── main.py                 the FastAPI entry point
        ├── config.py               options.json + environment variables
        ├── i18n.py                 the backend's message catalogue
        ├── runtime.py              process-wide state
        ├── api/                    HTTP routers
        ├── schemas/                pydantic request models
        ├── services/               ingest storage, queries, dashboard, devices, …
        ├── db/                     the SQLite layer and migrations
        ├── ingest/                 providers, the DNS wire parser, the ingest loop
        ├── categorization/         the rule engine and the built-in rule set
        ├── filters/                filter model → parameterised SQL
        ├── adguard/                the AdGuard client and Supervisor discovery
        ├── common/                 domain and time helpers
        └── static/                 the compiled frontend
```

---

## Performance

Measured over **1,000,000 records** with 234,857 distinct domains (a deliberately
pessimistic, long-tailed data set — a real DNS log has far fewer distinct
domains), on an Apple Silicon machine:

| Operation | Time |
|---|---|
| Ingest | 26,000 records/s |
| First page, no filter | 2 ms |
| ANY search (`googl` / `youtube` / `googlevideo`) | 96 ms |
| Nested AND/OR + a 24h window | 75 ms |
| Category filter | 3 ms |
| Deep paging (offset 10,000) | 3 ms |
| Dashboard, 24 hours | 50 ms |
| Dashboard, 7 days | 307 ms |
| Timeline, 30 days | 8 ms |
| Retention cleanup, deleting 500,000 records | 3.1 s |
| Database size | 264 MB |

What makes it fast:

* A `domain contains …` filter runs against the **`domains` table** (a few
  thousand rows), not against `queries`; the result is a set of `domain_id`s that
  the `queries` index can use. The same holds for client / person / tag /
  category filters.
* Conditions joined by `OR` that point at the same table are **merged into a
  single subquery**, so `domains` is read once rather than once per condition.
* The time-ordered page is selected **before the joins**, so the sort works on
  narrow rows (this is the 27 ms → 2 ms difference).
* Categorisation runs **once per domain**, not once per query.
* The timeline comes from a per-minute rollup table built during ingest.
* The dashboard's parts run **in parallel** on separate read connections.
* Retention cleanup is **delta-based**: it computes counter differences from the
  rows being deleted instead of recomputing every domain's counters (this is the
  310 s → 1.2 s difference).

A known limit: the `regex` operator cannot use an index, so it takes ~0.4 s over
a large domain table. Rarely used, and a documented trade-off.

---

## Privacy

* DNS history **never leaves the machine.** No telemetry, no external analytics,
  no cloud, no external AI API.
* The only outbound connections are to the Supervisor (`http://supervisor`) and
  to the AdGuard add-on's local address.
* Every frontend asset is compiled into the build — no CDN, no external fonts.
* The category lists live in the repository, offline; nothing is downloaded at
  runtime.
* Below `debug` level the add-on does not write queried domains to its own log.
* Every filter value travels as a bound SQL parameter — the filter engine never
  interpolates a value into the query text.
* Home Assistant handles the AdGuard password as a `password` field; the API only
  reports whether it is set.

---

## Licence

MIT — see [`LICENSE`](LICENSE).


---

# Magyar

[English](#adguard-log-viewer) · **Magyar**

DNS query log böngésző és elemző az [AdGuard Home][adguard]-hoz, **Home Assistant
OS add-onként**.

Nem egy szöveges log nézegető: a DNS forgalmat eszközök, személyek, kategóriák és
saját címkék mentén teszi kereshetővé, több millió rekord mellett is.

A felület a Home Assistant nyelvét követi — a magyar és az angol egyaránt
támogatott, az add-on beállítási oldalán és a webes felületen is.

---

## Tartalom

- [Mit tud](#mit-tud)
- [Nyelv](#nyelv)
- [Architektúra](#architektúra)
- [Home Assistant OS kompatibilitás](#home-assistant-os-kompatibilitás)
- [AdGuard integráció](#adguard-integráció)
- [Telepítés](#telepítés)
- [Konfiguráció](#konfiguráció)
- [Fejlesztői indítás](#fejlesztői-indítás)
- [Build](#build)
- [Tesztelés](#tesztelés)
- [Adatbázis](#adatbázis)
- [Mentés](#mentés)
- [Frissítés](#frissítés)
- [Projektstruktúra](#projektstruktúra)
- [Teljesítmény](#teljesítmény)
- [Adatvédelem](#adatvédelem)

---

## Mit tud

**Log nézet**

- Virtualizált táblázat, ki/bekapcsolható oszlopokkal — százezres sorszámnál is gyors.
- Minden rekordhoz: időpont, kliens IP, eszköznév, személy, domain, query típus
  (A / AAAA / CNAME / PTR / HTTPS / SVCB / …), válasz, DNS státusz, blokkolt vagy
  engedélyezett, AdGuard szabály és szűrőlista, válaszidő, upstream, protokoll,
  valamint az alkalmazás által adott kategóriák és címkék.
- Közel valós idejű frissítés Server-Sent Events-szel, automatikus polling
  fallbackkel. Csak a delta jön le, sosem a teljes log.

**Keresés és szűrés**

- Több keresési kifejezés egyszerre, **ANY (OR)** és **ALL (AND)** módban.
- Vizuális filter builder tetszőleges mélységű `(A OR B) AND (C OR D)` fákkal.
- Mezők: domain, registrable domain, kliens IP, eszköznév, személy, címke,
  kategória, query típus, blokkolt, DNS státusz, AdGuard reason, szabály,
  szűrőlista ID, upstream, válasz, válaszidő, időpont.
- Operátorok: equals, not equals, contains, not contains, starts with, ends with,
  regex, not regex, in list, not in list, >, ≥, <, ≤, is empty.
- Mentett szűrők: létrehozás, szerkesztés, átnevezés, törlés, egy kattintásos aktiválás.

**Kategorizálás**

- 96 beépített szabály, 89 címke és kategória (Google, YouTube, Meta, streaming,
  advertising, tracking, telemetry, AI, IoT, gaming, banking, hírek, …).
- Saját szabályok: suffix, exact, contains, starts/ends with, wildcard, regex;
  ANY vagy ALL módban, prioritással, beépített teszterrel.
- Kézi címkék domainenként, amiket az automatikus újraosztályozás nem ír felül.

**Eszközök és személyek**

- IP → saját név hozzárendelés, ami felülírja az AdGuard nevét.
- Több eszköz egy személyhez; szűrés egy vagy több személyre egyszerre.
- Devices oldal: IP, AdGuard név, saját név, személy, első/utolsó aktivitás,
  kérésszám, top domainek és kategóriák.

**Dashboard és részletező oldalak**

- Napi/órás/egyéni időszak, query timeline, blokkolt arány, top domainek,
  blokkolt domainek, eszközök, személyek, kategóriák, címkék, query típusok,
  upstream szerverek.
- Domain, eszköz és személy részletező oldalak saját idősorral és bontásokkal.

---

## Nyelv

Az add-on **magyarul és angolul** tud, és a Home Assistantot követi:

* **Az add-on Konfiguráció lapja.** A Home Assistant a `translations/en.yaml` és
  a `translations/hu.yaml` fájlból rajzolja ki, és a felhasználó nyelvéhez
  tartozót választja — nincs mit beállítani.
* **A webes felület.** Ingress alatt az oldal ugyanarról az origin-ről szolgál ki,
  mint a Home Assistant, így az alkalmazás elolvassa a körülötte lévő Home
  Assistant dokumentum `lang` attribútumát. Ez a felhasználó profiljában
  kiválasztott nyelvet tükrözi, nem csak a rendszerét. Home Assistanton kívül
  megnyitva a böngésző nyelvére, majd az angolra esik vissza.
* **A backend üzenetei** — validációs hibák, és az AdGuard elérésével kapcsolatos
  diagnosztika — ugyanazon a nyelven érkeznek: minden kérés visz egy
  `Accept-Language` fejlécet, a válasz pedig ehhez igazodik.
* **A dátumok, számok és relatív időpontok** is ezt a nyelvet követik, így egy
  magyar oldalon nem keverednek a magyar feliratok `09/19/2026` alakú
  időbélyegekkel.

A Settings → Megjelenés → Nyelv beállítás felhasználónként felülírja mindezt:
*Home Assistant szerint*, *English*, *Magyar*.

Egy harmadik nyelvhez egy `frontend/src/i18n/<kód>.ts`, egy szakasz az
`app/i18n.py`-ban és egy `translations/<kód>.yaml` kell. A szótárak az angolhoz
vannak típusozva, így egy hiányzó kulcs fordítási hiba, nem üres felirat; a
backend katalógusát ugyanígy a `tests/test_i18n.py` ellenőrzi.

---

## Architektúra

A teljes indoklás — és a Home Assistant OS korlátainak forráskód-szintű
ellenőrzése — az [`ARCHITECTURE.md`](ARCHITECTURE.md) fájlban van. Röviden:

```
AdGuard Home add-on            saját add-on
┌─────────────────┐            ┌──────────────────────────────────────┐
│ AdGuardHome     │            │ ingest loop                          │
│  127.0.0.1:45158│◀──nginx────│   AdGuardApiQueryLogProvider  ──┐    │
│                 │  :80/tcp   │   AdGuardFileQueryLogProvider ──┤    │
└─────────────────┘            │                                 ▼    │
         ▲                     │                        normalizálás  │
         │ Supervisor API      │                          + dedup     │
         │ felderítés          │                             ▼        │
┌─────────────────┐            │  SQLite (WAL)  ◀── kategorizálás      │
│ Supervisor      │◀───────────│     ▲                                │
└─────────────────┘            │     │ SQL szűrés / aggregáció        │
                               │  FastAPI  ──ingress──▶ React UI      │
                               └──────────────────────────────────────┘
```

| Réteg | Választás | Miért |
|---|---|---|
| Backend | Python 3.13 + FastAPI + uvicorn | Kicsi image a HA saját Alpine base-python image-ével; minden függőségnek van `musllinux` wheelje aarch64-re **és** x86_64-re, így a buildben nincs fordítás. |
| Adatbázis | SQLite (WAL), stdlib `sqlite3` | Egy fájl, nulla extra szolgáltatás, könnyen menthető. WAL mellett az író ingest és az olvasó API párhuzamosan fut. |
| Frontend | React 19 + TypeScript + Vite | Statikus build, amit a backend szolgál ki — nincs második futó folyamat. |
| Routing | hash routing | Ingress alatt a prefix dinamikus; hash routinggal soha nem kell az ingress path-t a frontendbe injektálni. |
| Realtime | SSE, polling fallbackkel | Egyirányú, proxy-barát, a WebSocketnél egyszerűbb. |

---

## Home Assistant OS kompatibilitás

Az AdGuard query log **host oldali** helye HA OS alatt:

```
/mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/data/querylog.json
```

**Ez az útvonal egy másik add-onból nem érhető el**, és nincs rá támogatott
megkerülés:

| Út | Működik? | Miért nem |
|---|---|---|
| Közvetlen fájlolvasás | ❌ | A `map:` kulcs csak `homeassistant_config`, `addon_config`, `all_addon_configs`, `ssl`, `addons`, `backup`, `share`, `media`, `data` típusokat ismer — egyik sem az idegen add-on `/data`-ja. |
| Supervisor API fájlhozzáférés | ❌ | Nincs ilyen végpont. |
| Supervisor ingress proxy | ❌ | Kötelező `ingress_session` cookie, amit `@require_home_assistant` miatt csak a HA Core hozhat létre. |
| AdGuard ingress nginx | ❌ | `allow 172.30.32.2; deny all;` — csak a Supervisor. |
| AdGuard API közvetlenül (`:45158`) | ❌ | `--host 127.0.0.1`, azaz a **host loopbackje**. |
| Backup/export + kicsomagolás | ⚠️ | Technikailag megy, de nem közel valós idejű és nagy I/O. Elutasítva. |
| **AdGuard „direct" web port + HTTP API** | ✅ | Ez az egyetlen támogatott, stabil út. |

Ezért az add-on **az AdGuard Home HTTP API-ját** használja. Cserébe egyszeri
beállítás kell az AdGuard add-onon: a *Web interface* (`80/tcp`) porthoz rendelj
egy hoszt portot. A lépések a [`DOCS.md`](adguard_log_viewer/DOCS.md) 2. pontjában.

A `file` provider megmarad Supervised / Container / Docker környezetre és
fejlesztéshez, de HA OS alatt nem az fut, és a Settings oldal jelzi, ha a megadott
fájl nem elérhető.

---

## AdGuard integráció

* **Semmi nincs beégetve.** Az `a0d7b954_adguard` azonosító csak egy fallback
  jelölt; a tényleges slug, IP és port futásidőben derül ki:
  `GET /discovery` → AdGuard slug → `GET /addons/<slug>/info` → `ip_address` +
  `network["80/tcp"]`. Mindkét végpont elérhető a legkisebb jogosultsággal
  (`hassio_role: default`).
* **Portot nem tippelünk.** A `80/tcp` az AdGuard konténer oldali portja; a
  hoszt port a felhasználó választása. Ha nem derül ki, az add-on nem talál ki
  egy címet, hanem a Settings oldalon lépésről lépésre megmutatja, mit nézett
  meg — és az `adguard_url` opcióval egy önmagában álló port is megadható.
* Az add-on **nem módosítja** az AdGuard add-on fájljait, konfigját vagy
  konténerét, és csak az AdGuard **verziózott HTTP API-ját** használja, nem a
  belső fájlformátumot — így egy AdGuard frissítés nem töri el.
* Az adatforrás a `QueryLogProvider` absztrakció mögött van
  (`AdGuardApiQueryLogProvider`, `AdGuardFileQueryLogProvider`), az alkalmazás
  többi része nem tudja, honnan jön az adat.

---

## Telepítés

1. **Beállítások → Kiegészítők → Kiegészítőtár → ⋮ → Tárolók** → add hozzá ennek
   a repónak az URL-jét.
2. Telepítsd az **AdGuard Log Viewer** add-ont.
3. Végezd el az [AdGuard egyszeri beállítását](adguard_log_viewer/DOCS.md#2-egyszeri-adguard-beállítás--ezt-hagyd-ki-és-semmi-nem-fog-működni).
4. Add meg a Home Assistant felhasználónevet és jelszót az add-on
   **Konfiguráció** fülén.
5. Indítsd el, és nyisd meg az oldalsávból.

## Konfiguráció

A teljes opciólista a [`DOCS.md`](adguard_log_viewer/DOCS.md#4-beállítások)-ban.
Két szint van:

* **Add-on options** (kapcsolat, poll interval, retention, log level) — ezeket a
  Home Assistant kezeli, újraindítást igényelnek.
* **Alkalmazás beállítások** (nyelv, téma, sűrűség, alapértelmezett időszak,
  oldalméret, retention felülírás, importálás ki/be) — a Settings oldalon,
  azonnali hatállyal.

Az opciók beolvasása közvetlenül a `/data/options.json`-ből történik
(`app/config.py`), nincs bashio shell réteg. Sorrend: környezeti változó →
s6 konténer környezet → add-on option → alapértelmezés.

---

## Fejlesztői indítás

Szükséges: Python 3.11+ és Node 20+.

```bash
# backend
cd adguard_log_viewer
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
DATA_DIR=./dev-data INGEST_ENABLED=false .venv/bin/python -m app.main
```

```bash
# frontend (külön terminál) — a /api hívásokat a 8099-re proxyzza
cd frontend
npm install
npm run dev
```

A backend a `http://127.0.0.1:8099` címen figyel, a Vite dev szerver az
`http://127.0.0.1:5173` címen.

Valódi AdGuard nélkül a Settings oldal jelzi, hogy a provider nem elérhető, de a
felület használható. Szintetikus adat generálásához lásd a `tools/benchmark.py`
szkriptet.

---

## Build

A frontend buildje a backend `app/static` könyvtárába kerül, és **a repóban
verziózva van** — így a Supervisor a HA eszközön csak Pythont telepít, nem kell
Node-ot futtatnia egy Raspberry Pi-n.

```bash
cd frontend
npm run build          # → adguard_log_viewer/app/static
```

Docker image (multi-arch):

```bash
cd adguard_log_viewer
docker build --build-arg BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21 -t aglv:aarch64 .
docker build --platform linux/amd64 --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21 -t aglv:amd64 .
```

A `pip install --only-binary :all:` miatt egy hiányzó wheel hangos build hiba
lesz, nem néma forrásfordítás. Az elérhetőség előre ellenőrizhető:

```bash
cd adguard_log_viewer
.venv/bin/python tools/check_wheels.py
```

---

## Tesztelés

```bash
cd adguard_log_viewer
.venv/bin/python -m pytest -q          # 368 teszt
.venv/bin/ruff check app tests tools
.venv/bin/mypy app
```

```bash
cd frontend
npm run typecheck
npm run lint
npm test
```

Lefedett területek: AdGuard API és fájl parser (a base64-es DNS wire formátum
dekódolásával együtt), deduplikáció, checkpoint és backfill logika, filter engine
(parse, AND/OR/NOT, minden operátor, SQL injection), domain matching, regex,
címke- és kategória-szabályok, IP → eszköz és eszköz → személy hozzárendelés,
retention cleanup, konfiguráció-rétegek, a teljes HTTP API, a biztonsági
korlátok (SQL injection minden szöveges mezőn, path traversal a statikus
kiszolgálón, lekérdezés-időkorlát, regex hossz), a **fordítás** (hogy a backend
minden üzenetének van magyar párja, és hogy a két frontend szótár kulcsai és
helyőrzői megegyeznek), valamint a **csomagolás**: hogy a beépített
szabálykészlet verziókövetve van-e, hogy a `config.yaml` átmegy-e a Supervisor
megkötésein, hogy az opciófordítások fedik-e a sémát, és hogy a lefordított
frontend jelen van-e.

A csomagolási tesztek azért vannak, mert két hiba csak telepítéskor derült ki:
egy horgonyozatlan `data/` minta a `.gitignore`-ban kizárta a beépített
szabályfájlt a repóból (lokálisan minden zöld volt, CI-ben 18 teszt bukott),
és egy `image: null` kulcs érvénytelenné tette a `config.yaml`-t, amitől az
add-on meg sem jelent a Kiegészítőtárban.

Teljesítménymérés szintetikus adaton:

```bash
cd adguard_log_viewer
.venv/bin/python tools/benchmark.py --records 1000000
```

---

## Adatbázis

SQLite, WAL módban, az add-on `/data` könyvtárában:
`/data/adguard_log_viewer.db`.

```
persons ── clients ── queries ── domains ── domain_tags ── tags
                                    │
rules   saved_filters   settings   ingest_state   stats_minute
```

Séma migrációk: `app/db/migrations.py`, `PRAGMA user_version` alapján,
append-only listaként. Kiadott migrációt soha nem szerkesztünk, csak újat adunk
hozzá — így a frissítés nem veszít adatot.

**Deduplikáció.** Az AdGuardnak nincs saját rekord-azonosítója, ezért minden
rekord kap egy stabil 64 bites `uid`-t a
`blake2b(ts_ns | client | domain | qtype)` értékből, amin `UNIQUE` index van. A
checkpoint csak optimalizáció; a helyességet az index garantálja, így
újraindítás, átfedő API oldal vagy logrotáció sem duplikál.

---

## Mentés

Az adatbázis az add-on `/data` könyvtárában van, amit a **Home Assistant backup
automatikusan visz**. Nagy adatbázisnál ez érezhetően növeli a mentés méretét —
ilyenkor csökkentsd a `retention_days` értéket.

Kézi mentés a hoszton:

```bash
ha addons stop adguard_log_viewer
# /mnt/data/supervisor/apps/data/<slug>/adguard_log_viewer.db másolása
ha addons start adguard_log_viewer
```

## Frissítés

Az add-on frissítésekor a séma automatikusan migrálódik. Az importált rekordok,
eszköznevek, személyek, címkék, szabályok és mentett szűrők megmaradnak. Az
AdGuard Home frissítése nem érinti az add-ont, mert csak a verziózott HTTP API-t
használjuk.

---

## Projektstruktúra

```
.
├── ARCHITECTURE.md                 architektúra és a HA OS korlátok elemzése
├── repository.yaml                 Home Assistant add-on repository leíró
├── .github/workflows/ci.yaml       lint, típusellenőrzés, teszt, wheel- és image-build
├── frontend/                       React + TypeScript forrás (csak fejlesztéshez)
│   └── src/
│       ├── api/                    HTTP kliens és végpontok
│       ├── components/             FilterBar, FilterBuilder, QueryTable, chart, UI
│       ├── i18n/                   magyar és angol szótárak
│       ├── pages/                  Dashboard, Log, Devices, People, Domains, Rules, …
│       ├── stores/                 app és filter állapot (zustand)
│       ├── hooks/                  adatlekérés, SSE élő frissítés
│       ├── types/                  a backend API típusai
│       └── utils/                  formázás
└── adguard_log_viewer/             az add-on (a Supervisor build kontextusa)
    ├── config.yaml  build.yaml  Dockerfile  DOCS.md  translations/
    ├── tests/                      pytest tesztek
    ├── tools/                      benchmark, szabálygenerátor, wheel ellenőrzés
    └── app/
        ├── main.py                 FastAPI belépési pont
        ├── config.py               options.json + környezeti változók
        ├── i18n.py                 a backend üzenetkatalógusa
        ├── runtime.py              process szintű állapot
        ├── api/                    HTTP routerek
        ├── schemas/                pydantic kérés modellek
        ├── services/               ingest tárolás, lekérdezés, dashboard, eszközök, …
        ├── db/                     SQLite réteg és migrációk
        ├── ingest/                 providerek, DNS wire parser, ingest loop
        ├── categorization/         szabálymotor és beépített szabálykészlet
        ├── filters/                filter modell → paraméterezett SQL
        ├── adguard/                AdGuard kliens és Supervisor felderítés
        ├── common/                 domain és idő segédfüggvények
        └── static/                 a lefordított frontend
```

---

## Teljesítmény

Mért értékek **1 000 000 rekordon**, 234 857 egyedi domainnel (ez egy szándékosan
pesszimista, hosszú farkú adathalmaz — valódi DNS logban jóval kevesebb az egyedi
domain), Apple Silicon gépen:

| Művelet | Idő |
|---|---|
| Ingest | 26 000 rekord/s |
| Első oldal, szűrő nélkül | 2 ms |
| ANY keresés (`googl` / `youtube` / `googlevideo`) | 96 ms |
| Beágyazott AND/OR + 24h ablak | 75 ms |
| Kategória szűrés | 3 ms |
| Mély lapozás (offset 10 000) | 3 ms |
| Dashboard, 24 óra | 50 ms |
| Dashboard, 7 nap | 307 ms |
| Timeline, 30 nap | 8 ms |
| Retention cleanup, 500 000 rekord törlése | 3,1 s |
| Adatbázis méret | 264 MB |

Mitől gyors:

* A `domain contains …` szűrés a **`domains` táblán** fut (néhány ezer sor), nem a
  `queries` táblán; az eredmény egy `domain_id` halmaz, amit a `queries` index
  használ. Ugyanez igaz a client / person / tag / category szűrésre.
* Az `OR`-ral kötött, ugyanarra a táblára mutató feltételek **egyetlen
  subquery-be vonódnak össze**, tehát a `domains` tábla egyszer olvasódik, nem
  feltételenként.
* Az idő szerint rendezett oldal a **join-ok előtt** választódik ki, így a
  rendezés keskeny sorokon dolgozik (ez hozta a 27 ms → 2 ms különbséget).
* A kategorizálás **domainenként egyszer** fut, nem lekérdezésenként.
* Az idővonal egy percenkénti rollup táblából jön, ami az ingest során épül.
* A dashboard részei külön read connection-ökön, **párhuzamosan** futnak.
* A retention cleanup **delta alapú**: a törlendő sorokból számol számláló-
  különbséget, nem számolja újra minden domain számlálóját (ez hozta a 310 s →
  1,2 s különbséget).

Ismert korlát: a `regex` operátor nem tud indexet használni, így nagy
domain-táblán ~0,4 s. Ritkán használt, dokumentált kompromisszum.

---

## Adatvédelem

* A DNS előzmény **nem hagyja el a gépet.** Nincs telemetria, nincs külső
  analytics, nincs felhő, nincs külső AI API.
* Hálózati kapcsolat csak a Supervisor (`http://supervisor`) és az AdGuard
  add-on lokális címe felé megy.
* A frontend minden asset-je a buildbe fordul — nincs CDN, nincs külső betűtípus.
* A kategória-listák a repóban vannak, offline; futásidőben semmit nem tölt le.
* Az add-on `debug` szint alatt nem írja a lekérdezett domaineket a saját logjába.
* Minden szűrőérték kötött SQL paraméterként megy — a filter engine nem
  interpolál értéket a lekérdezés szövegébe.
* Az AdGuard jelszót a Home Assistant `password` típusú mezőként kezeli; az API
  csak azt adja vissza, hogy be van-e állítva.

---

## Licenc

MIT — lásd [`LICENSE`](LICENSE).

[adguard]: https://github.com/AdguardTeam/AdGuardHome
