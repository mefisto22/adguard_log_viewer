# AdGuard Log Viewer

DNS query log böngésző és elemző az [AdGuard Home][adguard]-hoz, **Home Assistant
OS add-onként**.

Nem egy szöveges log nézegető: a DNS forgalmat eszközök, személyek, kategóriák és
saját címkék mentén teszi kereshetővé, több millió rekord mellett is.

---

## Tartalom

- [Mit tud](#mit-tud)
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
* **Alkalmazás beállítások** (téma, sűrűség, alapértelmezett időszak,
  oldalméret, retention felülírás, importálás ki/be) — a Settings oldalon,
  azonnali hatállyal.

Az opciók beolvasása közvetlenül a `/data/options.json`-ből történik
(`app/config.py`), nincs bashio shell réteg. Sorrend: környezeti változó →
add-on option → alapértelmezés.

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
.venv/bin/python -m pytest -q          # 291 teszt
.venv/bin/ruff check app tests tools
.venv/bin/mypy app
```

```bash
cd frontend
npm run typecheck
npm run lint
```

Lefedett területek: AdGuard API és fájl parser (a base64-es DNS wire formátum
dekódolásával együtt), deduplikáció, checkpoint és backfill logika, filter engine
(parse, AND/OR/NOT, minden operátor, SQL injection), domain matching, regex,
címke- és kategória-szabályok, IP → eszköz és eszköz → személy hozzárendelés,
retention cleanup, konfiguráció-rétegek, a teljes HTTP API, a biztonsági
korlátok (SQL injection minden szöveges mezőn, path traversal a statikus
kiszolgálón, lekérdezés-időkorlát, regex hossz), valamint a **csomagolás**:
hogy a beépített szabálykészlet verziókövetve van-e, hogy a `config.yaml`
átmegy-e a Supervisor megkötésein, és hogy a lefordított frontend jelen van-e.

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
