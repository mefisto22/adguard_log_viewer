# ARCHITECTURE — AdGuard Log Viewer (Home Assistant OS alkalmazás)

Ez a dokumentum rögzíti, hogyan férünk hozzá az AdGuard Home query loghoz
**Home Assistant OS** alatt, és miért pont úgy. A döntések nem feltételezésen,
hanem a Supervisor és a hivatalos AdGuard Home alkalmazás **forráskódjának**
ellenőrzésén alapulnak (a hivatkozott fájlok a dokumentum végén).

---

## 1. A kiindulási kérdés

A felvetett host oldali útvonal:

```
/mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/data/querylog.json
```

Ez az AdGuard Home alkalmazás **saját `/data` könyvtára** a HA OS host filesystemén
(a Supervisor minden alkalmazás `/data`-ját itt tartja). A kérdés: elérheti-e ezt egy
másik, saját alkalmazás?

**Rövid válasz: nem, támogatott módon nem.** Az alábbi táblázat a HA OS alatt
ténylegesen létező összes hozzáférési utat végigveszi.

---

## 2. Hozzáférési utak kiértékelése

| # | Út | Működik HA OS alatt? | Indoklás |
|---|----|----------------------|----------|
| 1 | Közvetlen fájlolvasás az AdGuard `/data`-jából | ❌ **Nem** | A `config.yaml` `map:` kulcsa csak ezeket a típusokat ismeri: `homeassistant_config`, `addon_config`, `all_addon_configs`, `ssl`, `addons`, `backup`, `share`, `media`, `data`. Egyik sem az *idegen alkalmazás* `/data` könyvtára. A `data` a **saját** perzisztens tárunk, az `all_addon_configs` pedig a `/addon_configs/<slug>` *config* mappákat adja — az AdGuard viszont a `/data/adguard/data/` alá ír, nem a config mappába. Nincs támogatott bind mount erre az útvonalra. |
| 2 | Supervisor API fájlhozzáférés | ❌ **Nem** | A Supervisor REST API-ban nincs olyan végpont, amely egy alkalmazás `/data`-jából fájlt adna vissza. |
| 3 | Supervisor **ingress proxy** (`GET /ingress/{token}/...`) | ❌ **Nem** | A handler kötelezően érvényes `ingress_session` cookie-t vár, és a session létrehozása (`POST /ingress/session`) `@require_home_assistant` dekorátorral védett — **kizárólag a Home Assistant Core** hozhat létre ingress sessiont, alkalmazás nem. |
| 4 | Az AdGuard alkalmazás **ingress nginx** portja közvetlenül | ❌ **Nem** | Az alkalmazás `ingress.gtpl` sablonja `allow 172.30.32.2; deny all;` — csak a Supervisor IP-je engedélyezett. A mi alkalmazásunk a `172.30.32.0/23` hálózat más címét kapja, így elutasításra kerül. |
| 5 | Az AdGuard **HTTP API közvetlenül** (`45158`) | ❌ **Nem** | Az alkalmazás `AdGuardHome`-ot `--host 127.0.0.1 --port 45158` paraméterrel indítja. A `host_network: true` miatt ez a **host loopbackje**, amely egy másik konténer network namespace-éből elvileg sem érhető el. |
| 6 | Supervisor backup / partial snapshot + kicsomagolás | ⚠️ Technikailag lehetséges, de **elutasítva** | Teljes alkalmazás backup készítése percenként nem közel valós idejű, nagy I/O terhelés, `hot`/`cold` backup mellékhatásokkal. Nem stabil alap egy log viewerhez. |
| 7 | HA Core AdGuard **integráció** | ❌ **Nem** | Csak statisztikai szenzorokat (queries/blocked/…) ad, query log rekordokat nem. |
| 8 | **AdGuard alkalmazás „direct" webfelület portja + AdGuard HTTP API** | ✅ **Igen** | Ez az egyetlen támogatott, stabil út. Részletek alább. |

### 2.1 A választott megoldás (8): AdGuard HTTP API a „direct" porton

A hivatalos AdGuard Home alkalmazás nginx-et futtat két server blokkal:

* **ingress server** — csak a Supervisornak (`allow 172.30.32.2`),
* **direct server** — *csak akkor jön létre*, ha a felhasználó hoszt portot rendel
  a `80/tcp`-hez az AdGuard alkalmazás „Network" beállításánál (alapból `null`).

A direct server az AdGuard teljes HTTP API-ját proxyzza (`proxy_pass ... backend`,
ahol `backend = 127.0.0.1:45158`). Mivel az AdGuard alkalmazás `host_network: true`,
ez a port a **hoszton** nyílik meg, amit a mi alkalmazásunk a hassio bridge gateway-én
(`172.30.32.1`) keresztül elér.

**Hitelesítés.** A direct server alapértelmezésben `auth_request`-tel a Supervisor
`/auth` végpontjához fordul, amely elfogadja a HTTP **Basic auth** fejlécet, és a
**Home Assistant felhasználó** nevét/jelszavát ellenőrzi. Ezért:

* ha az AdGuard alkalmazás `leave_front_door_open: false` (alapértelmezés) →
  a `username`/`password` egy **Home Assistant felhasználó** hitelesítő adata;
* ha `leave_front_door_open: true` → az nginx nem kér HA auth-ot, és csak az
  AdGuard Home saját felhasználói (ha be vannak állítva) számítanak.

Mindkét eset ugyanaz a kódút: Basic auth opcionális felhasználónévvel/jelszóval.

### 2.2 Miért nem törik el AdGuard frissítéskor

* Nem nyúlunk az AdGuard alkalmazás fájljaihoz, konfigjához, konténeréhez.
* Csak az AdGuard Home **stabil, verziózott HTTP API-ját** használjuk
  (`GET /control/querylog`), nem a belső fájlformátumot.
* A slug, IP és port **futásidőben, Supervisor API-ból derül ki** (lásd 3.),
  nincs beégetve.

### 2.3 Amit a felhasználónak egyszer be kell állítania

Az AdGuard Home alkalmazás „Network" szekciójában a **Web interface (80/tcp)** porthoz
kell egy hoszt port — bármelyik szabad. Ez a Home Assistant saját felületéről támogatott,
dokumentált beállítás — nem hack, nem módosítja az alkalmazás működését. A README `Telepítés`
fejezete végigvezet rajta.

---

## 3. Automatikus felderítés (nincs beégetett slug)

Az `a0d7b954_adguard` azonosító **egyetlen helyen sem kötelező**. A felderítés
sorrendje (`adguard_log_viewer/app/adguard/discovery.py`):

1. Ha a felhasználó megadott explicit `adguard_url`-t → azt használjuk.
2. `GET http://supervisor/discovery` (Bearer `SUPERVISOR_TOKEN`) — az AdGuard
   alkalmazás `adguard` típusú discovery üzenetet küld, amiből megkapjuk a **slugját**.
   Ez a végpont a Supervisor `api_bypass` listáján van, tehát `hassio_role: default`
   mellett is elérhető.
3. `GET http://supervisor/addons/<slug>/info` → `ip_address` (host_network alkalmazás
   esetén `172.30.32.1`) és `network` (pl. `{"53/udp": 53, "80/tcp": 9876}`), ahonnan a
   felhasználó által választott **hoszt** port derül ki.
4. Ha a discovery nem ad találatot, végigpróbáljuk a jelöltek listáját
   (`a0d7b954_adguard`, `adguard`, `core_adguard`, …) a `/addons/<slug>/info`
   végponton — ez `ROLE_DEFAULT` mellett is engedélyezett (`^/.+/info$`).
5. Ha a port így sem derül ki, **nem tippelünk**. A `80/tcp` az AdGuard
   *konténer* oldali portja; a hoszt port a felhasználó választása, amire nincs
   értelmes alapérték. Korábban ide `http://172.30.32.1:3000` került, ami minden
   hibát egy olyan portra mutató üzenetté alakított, aminek semmi köze a
   beállításhoz. Helyette az `url` `None` lesz, a felderítés lépései pedig
   megjelennek a Settings oldalon.

A `normalize_url` elfogadja a rövidítéseket is: egy önmagában álló port a
hassio gateway adott portját jelenti (`9000` → `http://172.30.32.1:9000`).

Így az alkalmazás újratelepítés/átnevezés/frissítés után is megtalálja az AdGuardot.

---

## 4. Provider absztrakció

Az alkalmazás többi része **nem tudja**, honnan jön az adat:

```
QueryLogProvider (ABC)
├── AdGuardApiQueryLogProvider    # HA OS alapértelmezés — HTTP API
└── AdGuardFileQueryLogProvider   # querylog.json közvetlen olvasás
```

A `AdGuardFileQueryLogProvider` **nem HA OS-re** készült, hanem:

* HA Supervised / HA Container / sima Docker környezetre, ahol a fájl bind
  mountolható,
* fejlesztéshez és teszteléshez,
* jövőbeli kompatibilitáshoz, ha a HA egyszer kínál támogatott megosztást.

Teljesíti a „ne feltételezd, hogy másik konténer eléri a host path-t" kikötést:
HA OS alatt alapértelmezésben **nem** ez fut, és a Settings oldal figyelmeztet,
ha a megadott fájl nem elérhető.

Mindkét provider ugyanazt a normalizált `QueryRecord` struktúrát adja vissza
(`adguard_log_viewer/app/ingest/records.py`), így a downstream kód egységes.

### 4.1 Inkrementális ingest

Az AdGuard API-nak nincs „newer_than" paramétere, csak `older_than` (visszafelé
lapozás). Az ingest ezért:

1. lekéri a legfrissebb oldalt (`limit=batch_size`),
2. amíg olyan rekordot lát, ami újabb a checkpointnál, `older_than=<oldest>`
   paraméterrel lapoz visszafelé,
3. megáll, ha eléri a checkpointot, vagy a `max_pages_per_poll` határt.

Így egy poll ciklus a **delta** méretével arányos, nem a teljes log méretével.

A fájl provider byte offset + inode alapú tailinget használ, logrotációt detektál.

### 4.2 Deduplikáció

Minden rekordhoz stabil `uid` készül:

```
uid = int64( blake2b( ts_ns | client | qname | qtype , digest_size=8 ) )
```

A `queries.uid` oszlopon `UNIQUE` index van, az insert `INSERT OR IGNORE`.
Ez akkor is helyes, ha ugyanaz az oldal többször jön le (API átfedés,
újraindítás, logrotáció). A checkpoint (`ingest_state`) csak optimalizáció —
a helyességet a UNIQUE index garantálja.

---

## 5. Technológiai döntések

| Réteg | Választás | Indoklás |
|-------|-----------|----------|
| Backend | **Python 3.13 + FastAPI + uvicorn** | Kicsi image az HA saját `base-python` Alpine image-ével; a szükséges wheelek (`pydantic-core`) léteznek `musllinux` aarch64 **és** x86_64 változatban → nincs fordítás build közben. Jó async I/O, egyszerű karbantartás. |
| Adatbázis | **SQLite (WAL) stdlib `sqlite3`** | Nulla extra szolgáltatás, egy fájl, könnyen menthető. WAL mellett az író ingest és az olvasó API párhuzamosan fut. Több millió rekordig jól skálázódik megfelelő indexekkel. |
| HTTP kliens | **httpx** | Tiszta Python, async, timeout/retry kezelés. |
| Frontend | **React 19 + TypeScript + Vite** | Statikus buildet ad, amit a backend szolgál ki — nincs második futó folyamat. TS a bővíthető filter modellhez. |
| Virtualizáció | **@tanstack/react-virtual** | Százezres soros táblához is elég. |
| Routing | **hash routing** (`#/devices`) | HA ingress alatt az alkalmazás egy dinamikus prefix alatt fut (`/api/hassio_ingress/<token>/`). Hash routinggal a base path soha nem változik → nem kell az ingress path-t a frontendbe injektálni. |
| Realtime | **SSE** (`ingress_stream: true`), polling fallback | A WebSocketnél egyszerűbb, egyirányú, proxy-barát. A stream csak **értesítést** küld; a delta lekérést a kliens a normál, szűrt API-n végzi → sosem megy le a teljes log. |
| Base image | `ghcr.io/home-assistant/{arch}-base-python:3.13-alpine3.21` | Hivatalos HA base, s6-overlay v3 + bashio, multi-arch (aarch64 + amd64). |

---

## 6. Adatmodell (áttekintés)

A séma **normalizált**, mert ez a teljesítmény kulcsa:

```
persons(id, name, color)
clients(id, ip, adguard_name, alias, person_id, first_seen_ns, last_seen_ns, query_count)
domains(id, name, registrable, first_seen_ns, last_seen_ns, query_count, classified_at)
tags(id, name, kind['tag'|'category'], color, builtin)
domain_tags(domain_id, tag_id, source['builtin'|'rule'|'manual'])
queries(id, uid UNIQUE, ts_ns, domain_id, client_id, qtype, qclass, status,
        reason, blocked, rule_text, filter_list_id, elapsed_us, upstream,
        cached, answer, answers_json, client_proto)
rules(id, name, enabled, priority, conditions_json, tags_json)
saved_filters(id, name, filter_json, created_at, updated_at)
settings(key, value)
ingest_state(key, value)
```

**Miért gyors:**

* A `domain contains 'googl'` szűrés a **`domains` táblán** fut (néhány ezer sor),
  nem a `queries` táblán (több millió sor). Az eredmény egy `domain_id` halmaz,
  amit a `queries.domain_id` index használ:
  `q.domain_id IN (SELECT id FROM domains WHERE name LIKE ?)`.
* Ugyanez igaz a client / person / tag / category szűrésre.
* A kategorizálás **domainenként egyszer** fut (`domains.classified_at`), nem
  query-nként. Egy új domain megjelenésekor osztályozunk, utána csak join.
* Indexek: `queries(ts_ns)`, `queries(domain_id, ts_ns)`, `queries(client_id, ts_ns)`,
  `queries(blocked, ts_ns)`, `queries(uid)`.

---

## 7. Filter engine

A szűrő egy **JSON AST**, amit a backend paraméterezett SQL-re fordít
(`adguard_log_viewer/app/filters/`):

```jsonc
{ "op": "and", "children": [
    { "op": "or", "children": [
        { "field": "domain", "operator": "contains", "value": "youtube" },
        { "field": "domain", "operator": "contains", "value": "googlevideo" } ] },
    { "op": "or", "children": [
        { "field": "person", "operator": "equals", "value": "Péter" },
        { "field": "person", "operator": "equals", "value": "Anna" } ] },
    { "field": "timestamp", "operator": "gte", "value": "now-24h" } ] }
```

* Tetszőleges mélységű `and` / `or` / `not` csoportok.
* Minden érték **kötött paraméter** — SQL injection kizárva.
* `regex` operátorhoz saját `REGEXP` SQLite függvény (dokumentáltan index nélküli).
* A gyors „több feltétel egyszerre" keresés (ANY/ALL) ugyanennek az AST-nek
  egy egyszerűsített felülete — nincs külön kódút.

---

## 7.1 Miért az alkalmazás könyvtárban van a backend

A Supervisor az alkalmazás **saját könyvtárát** használja Docker build kontextusként,
tehát a `Dockerfile` csak azon belülről tud másolni. Ezért az alkalmazás forrása
az `adguard_log_viewer/` könyvtárban él, nem egy külön `backend/` mappában — így
a repó közvetlenül telepíthető Home Assistantba, külön CI vagy registry nélkül.

A frontend forrása a repó gyökerében marad (`frontend/`), a lefordított
kimenete viszont az `adguard_log_viewer/app/static` alatt **verziózva van**.
Így a Supervisor a HA eszközön csak Pythont telepít, nem kell Node-ot és `npm
install`-t futtatnia egy Raspberry Pi-n.

---

## 8. Home Assistant integráció

* **Ingress**: `ingress: true`, `ingress_port: 8099`, `ingress_stream: true`.
  Az alkalmazás a HA oldalsávból nyílik, külön port publikálása nélkül.
* **Perzisztens tár**: minden adat az alkalmazás `/data` könyvtárában
  (`/data/adguard_log_viewer.db`), így frissítés/újraindítás után megmarad,
  és a HA backup automatikusan viszi.
* **Supervisor API**: `hassio_api: true`, `hassio_role: default` — a lehető
  legkisebb jogosultság, ami a felderítéshez kell.
* **Konfiguráció**: alkalmazás options (kapcsolat, poll interval, retention, timezone,
  batch méret) + alkalmazáson belüli Settings oldal (tagek, szabályok, aliasok,
  személyek). A jelszó `password` típusú a sémában, így a HA maszkolja és nem
  írja logba.
* **Multi-arch**: `aarch64` és `amd64` build (`build.yaml`), a HA base image
  `{arch}` behelyettesítésével.

---

## 8.1 s6-overlay és a környezeti változók

A Home Assistant base image **s6-overlay**-t használ initként. Az s6 az általa
indított folyamatnak **üres környezetet** ad: a konténer valódi környezetét a
`/run/s6/container_environment/` könyvtárba menti, és `with-contenv`-vel kell
visszaolvasni.

Ez nem kozmetikai részlet: enélkül az alkalmazás nem látja a `SUPERVISOR_TOKEN`-t,
tehát **egyáltalán nem tudja megkérdezni a Supervisort**, hol fut az AdGuard —
az automatikus felderítés csendben minden telepítésen elbukik. A `TZ` sem jut
át, így minden időbélyeg UTC lesz.

Ezért a `CMD` `with-contenv`-en keresztül indul, és az `app/config.py`
tartalékként közvetlenül is olvassa a `/run/s6/container_environment/`
könyvtárat — így a beállítás akkor is helyes, ha az image-et máshogy indítják.

---

## 9. Biztonság és adatvédelem

* **Semmilyen DNS adat nem hagyja el a gépet.** Nincs telemetria, nincs külső
  analytics, nincs külső AI API, nincs CDN a frontendben (minden asset a
  buildbe fordul).
* Hálózati kapcsolatot kizárólag két cél felé nyitunk:
  a Supervisor (`http://supervisor`) és az AdGuard alkalmazás lokális címe.
* A beépített kategória-listák **a repóban, offline** vannak; nincs futásidejű
  letöltés. Opcionális külső lista importja kézi, explicit művelet.
* Az alkalmazás saját logja alapértelmezésben **nem írja ki a lekérdezett
  domaineket**; ez csak `debug` log szinten történik, külön figyelmeztetéssel.
* Az ingress miatt a hozzáférést a Home Assistant saját felhasználókezelése védi.
* Minden szűrőérték **kötött SQL paraméterként** megy; a filter engine sosem
  interpolál értéket a lekérdezés szövegébe, az oszlopnevek pedig egy rögzített
  regiszterből jönnek.
* Az olvasó lekérdezéseknek **határidejük van** (`DEFAULT_READ_TIMEOUT`, 30 s),
  amit egy SQLite progress handler érvényesít. A felhasználó által megadott
  reguláris kifejezést a motor soronként értékeli ki, és a Python `re`-nek nincs
  saját időkorlátja — e nélkül egy patológiás minta percekre lefoglalhatna egy
  worker szálat. A minta hossza ezen felül 500 karakterre korlátozott.

---

## 10. Hivatkozott források (ellenőrizve)

* HA alkalmazás config referencia (`map`, `ingress`, `hassio_role`, sémák):
  <https://developers.home-assistant.io/docs/add-ons/configuration/>
* AdGuard Home alkalmazás `config.yaml` (host_network, ingress, `80/tcp: null`,
  `backup_exclude: */adguard/data/querylog.*`):
  `hassio-addons/addon-adguard-home` → `adguard/config.yaml`
* AdGuard indítási paraméterek (`--host 127.0.0.1 --port 45158`):
  `adguard/rootfs/etc/s6-overlay/s6-rc.d/adguard/run`
* nginx ingress/direct sablonok (`allow 172.30.32.2`, `auth_request /authentication`):
  `adguard/rootfs/etc/nginx/templates/{ingress,direct}.gtpl`
* Supervisor ingress session korlátozás (`@require_home_assistant`):
  `home-assistant/supervisor` → `supervisor/api/ingress.py`
* Supervisor szerepkör-szabályok (`ROLE_DEFAULT: ^/.+/info$`, `api_bypass: /discovery.*`):
  `supervisor/api/middleware/security.py`
* AdGuard Home query log API szerződés (`older_than`, `limit`, `QueryLogItem`):
  `AdguardTeam/AdGuardHome` → `openapi/openapi.yaml`
