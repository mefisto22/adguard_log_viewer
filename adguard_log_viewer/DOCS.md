# AdGuard Log Viewer — user guide

**English** · [Magyar](#adguard-log-viewer--használati-útmutató)

A DNS query log viewer and analyzer for AdGuard Home, as a Home Assistant add-on.

The add-on speaks English and Hungarian and follows Home Assistant's language,
both on this Configuration page and in the web interface. Settings → Appearance →
Language overrides it per user.

---

## 1. What you need

* **Home Assistant OS** (or Supervised), with the Supervisor.
* The **official AdGuard Home add-on**, installed and running.
* The **query log turned on** in AdGuard Home
  (AdGuard → Settings → General settings → *Logs configuration*).

---

## 2. One-time AdGuard setup — skip this and nothing will work

Under Home Assistant OS an add-on **cannot read another add-on's data
directory**, so `querylog.json` is out of reach. This add-on therefore uses
AdGuard Home's **HTTP API**, which is only reachable once the AdGuard add-on's
web port is published. (The reasoning in full: `ARCHITECTURE.md`.)

1. Home Assistant → **Settings → Add-ons → AdGuard Home**.
2. The **Configuration** tab → the **Network** section.
3. Enter a free host port next to **Web interface** (`80/tcp`).
4. **Save**, then **restart** the AdGuard Home add-on.

> `80/tcp` is AdGuard's **container** port — that one is fixed. What you type
> beside it is the **host** port, and it can be anything. There is no "default"
> value: this add-on uses the port you chose, because it asks the Supervisor for
> it. If a port is already set, leave it alone and use that one.

This is a supported, documented Home Assistant setting — it does not change how
the AdGuard add-on works, and it survives an update.

### Or give the address directly

If you would rather not publish the port, or AdGuard does not run under Home
Assistant, put the address in this add-on's **AdGuard Home URL** option. **This
is not a workaround**; it is an equally supported route. Accepted forms:

| What you type | What it means |
|---|---|
| `9000` or `:9000` | port 9000 on the Home Assistant host |
| `192.168.1.5:9000` | another machine |
| `http://adguard.local:9000` | a full URL |
| `https://adguard.example` | HTTPS (see the `adguard_verify_ssl` option) |

### Do I need a username and password?

By default the AdGuard add-on protects that port with **Home Assistant login**.
So:

| The AdGuard add-on's `leave_front_door_open` | What to give this add-on |
|---|---|
| `false` (the default) | The name and password of a **Home Assistant user** |
| `true` | Leave it empty, or use AdGuard's own user if you have one |

> **Tip:** create a separate HA user for this (`adguard-log-viewer`, say) rather
> than using your own admin account.

---

## 3. Installation

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Add this repository's URL.
3. Install the **AdGuard Log Viewer** add-on.
4. On the **Configuration** tab, enter the username and password (see above).
5. **Start**, then **Open Web UI** — or use the sidebar, if you turn on
   *Show in sidebar*.

On its first start the add-on reads AdGuard's log backwards as far as the
retention limit (`retention_days`). That can take a few minutes; the interface is
usable meanwhile, and data keeps appearing.

---

## 4. Options

| Option | Default | Description |
|---|---|---|
| `adguard_url` | *(empty)* | The address you open AdGuard at. Left empty it is asked of the Supervisor — which needs the AdGuard add-on to publish `80/tcp`. If it does not, put the address here; a bare port (`9000`) is enough. |
| `adguard_username` | *(empty)* | A Home Assistant username (see section 2). |
| `adguard_password` | *(empty)* | Its password. Home Assistant masks it and the add-on never logs it. |
| `adguard_verify_ssl` | `false` | Turn this on only if AdGuard is reachable over HTTPS with a valid certificate. |
| `adguard_slug` | *(empty)* | Only if auto-discovery would find the wrong add-on (e.g. `a0d7b954_adguard`). |
| `provider` | `auto` | `api` = AdGuard's HTTP API (the only one that works under HA OS), `file` = reading `querylog.json` directly. |
| `querylog_path` | *(empty)* | For the `file` source only. Leave empty under HA OS. |
| `poll_interval` | `10` | How many seconds between fetches of new records. |
| `ingest_batch_size` | `500` | Records per API call. |
| `max_pages_per_poll` | `20` | An upper bound on one poll's work. Older history arrives on later rounds. |
| `ingest_enabled` | `true` | Turned off, importing stops but the interface stays usable. |
| `retention_days` | `30` | How many days of history to keep. `0` = unlimited. Can also be overridden from the Settings page. |
| `log_level` | `info` | At `debug` the add-on may log queried domains — for troubleshooting only. |

What the **Settings** page changes without a restart: language, theme, density,
default period, page size, retention, ingest on/off. The add-on options appear
there read-only.

---

## 5. Using it

### Searching on several terms

You can type several terms into the search box — each becomes its own chip with
**Enter**. Past two terms an **ANY / ALL** switch appears:

* **ANY** — queries containing *at least one* of them
  (say `googl`, `youtube`, `googlevideo`);
* **ALL** — only those containing *all* of them.

The dropdown beside the search box picks what to search: domain, client IP,
device name, answer, filter rule, or every field.

### The advanced filter

The **Advanced** button builds an AND/OR condition tree of any depth, such as:

```
(domain contains "youtube" OR domain contains "googlevideo")
AND (person = "Péter" OR person = "Anna")
AND timestamp >= now-24h
```

The whole filter runs on the server, in SQL — the browser never receives more
data than it displays.

### Saved filters

The **Save** button on the filter bar stores the current filter. On the **Saved
filters** page it can be renamed, edited, deleted and applied in one click.

### Devices and people

* **Devices** — every client IP AdGuard has seen. You can give it your own name
  (which overrides AdGuard's) and assign it to a person.
* **People** — one person can own several devices. After that a single filter
  shows all their traffic, and several people can be selected at once.

### Tags and categories

Every domain is tagged automatically from a built-in rule set (Google, YouTube,
Advertising, Telemetry, IoT, News, …). On the **Rules** page you can add your own:

```
Name:        Work
Conditions:  domain contains "intranet"
             OR domain endsWith "corp.local"
Tags:        Work (category), Work laptop (tag)
```

Before saving a rule, the **Try it** box tries it against a domain you name.
After a rule change the domains it affects are re-classified in the background;
**Settings → Re-classify all domains** forces it immediately.

You can also tag a single domain by hand on its detail page; manual tags
**survive** rule changes.

---

## 6. Troubleshooting

### The add-on does not appear after adding the repository

If the Add-on Store shows the repository but it is empty, or the add-on is
missing, the Supervisor **rejected `config.yaml`** — and does not say so in the
interface. The Supervisor log gives the reason:

**Settings → System → Logs**, pick the **Supervisor** log from the dropdown at
the top, and search for the add-on's name. A rejected configuration looks like
this:

```
Can't read config for ... : expected a non-empty string for docker image
```

Worth checking:

1. **Reload the repository.** Add-on Store → ⋮ → *Check for updates*. The
   Supervisor caches repositories, so a fix does not show up straight after a
   push. From the command line: `ha addons reload`.
2. **Architecture.** This add-on runs on `aarch64` and `amd64` machines. If your
   Home Assistant is `armv7` or `i386` (an older Raspberry Pi, a 32-bit system)
   it will not be listed. Check under **Settings → System → About**.
3. **Whether the repository is reachable.** The Supervisor cannot fetch a private
   GitHub repository; it has to be public, or carry credentials.

### "AdGuard Home is not reachable"

The **Settings** page says what the add-on can see. The usual causes:

| Symptom | Cause | Fix |
|---|---|---|
| `The AdGuard Home address could not be worked out` | The AdGuard add-on publishes no host port for `80/tcp` | Section 2: set a port, **or** give `adguard_url`. The Settings page's **How it was looked up** row shows step by step what was found, and which ports the Supervisor reports for the AdGuard add-on |
| `Cannot reach AdGuard Home at <address>` | The address is known but does not answer | Check that AdGuard is running, and really reachable on that port |
| `HTTP 401` or `403` | Missing or wrong credentials | Give a valid **Home Assistant** user and password |
| `returned text/html instead of JSON` | The request was caught by nginx's login layer | The same: the username or password is wrong |
| `No AdGuard Home add-on was found` | Discovery found no AdGuard | Set `adguard_url` by hand |

### No new records arrive

* Look at the *Last poll* row on the **Settings** page.
* Check that the query log is enabled in AdGuard Home — the add-on warns
  separately when it is not.
* Make sure **Import new queries from AdGuard** is not turned off.

### Live updates do not work

The interface uses Server-Sent Events. If the stream cannot be established the
add-on falls back to polling every 15 seconds — the *Live* indicator stays green,
it just refreshes more slowly.

### The database is large

The **Settings → Database** section shows its size. Lower `retention_days`, then
press **Run cleanup now**.

---

## 7. Privacy

* DNS history **never leaves the machine**. No telemetry, no external analytics,
  no cloud, no external AI API.
* There are only two outbound destinations: the Supervisor (`http://supervisor`)
  and the AdGuard add-on's local address.
* The category lists live in the repository, offline — nothing is downloaded at
  runtime.
* Below `debug` level the add-on does not write queried domains to its log.
* The interface is protected by Home Assistant's own user management (ingress).
  If you publish port `8099/tcp`, that port is **not** protected by HA login.

---

## 8. Backups and upgrades

* All data lives in the add-on's `/data` directory
  (`/data/adguard_log_viewer.db`), which **Home Assistant's backup takes
  automatically**. With a large database that noticeably grows the backup — pick
  a smaller `retention_days` if it does.
* On an upgrade the database schema migrates automatically; imported records,
  device names, people, tags and saved filters are all kept.

---

# AdGuard Log Viewer — használati útmutató

[English](#adguard-log-viewer--user-guide) · **Magyar**

DNS query log böngésző és elemző az AdGuard Home-hoz, Home Assistant add-onként.

Az add-on magyarul és angolul tud, és a Home Assistant nyelvét követi — ezen a
Konfiguráció lapon és a webes felületen egyaránt. A Settings → Megjelenés →
Nyelv beállítás felhasználónként felülírja.

---

## 1. Mire van szükség

* **Home Assistant OS** (vagy Supervised), Supervisorral.
* A **hivatalos AdGuard Home add-on** telepítve és futva.
* Az AdGuard Home-ban a **query log legyen bekapcsolva**
  (AdGuard → Settings → General settings → *Logs configuration*).

---

## 2. Egyszeri AdGuard beállítás — ezt hagyd ki, és semmi nem fog működni

Home Assistant OS alatt egy add-on **nem tudja olvasni egy másik add-on
adatkönyvtárát**, tehát a `querylog.json` fájlt közvetlenül nem érjük el. Ezért
ez az add-on az AdGuard Home **HTTP API-ját** használja, amit viszont csak akkor
lehet elérni, ha az AdGuard add-on webes portja publikálva van. (A miértek
részletesen: `ARCHITECTURE.md`.)

1. Home Assistant → **Beállítások → Kiegészítők → AdGuard Home**.
2. **Konfiguráció** fül → **Hálózat** szekció.
3. A **Web interface** (`80/tcp`) sorba írj be egy szabad hoszt portot.
4. **Mentés**, majd az AdGuard Home add-on **újraindítása**.

> A `80/tcp` az AdGuard **konténer** oldali portja — ez fix. Amit te beírsz
> mellé, az a **hoszt** port, és bármi lehet. Nincs „alapértelmezett" érték:
> ez az add-on azt a portot használja, amit te megadtál, mert a Supervisortól
> kérdezi le. Ha már be van állítva egy port, ne írd át — használd azt.

Ez támogatott, dokumentált Home Assistant beállítás — nem módosítja az AdGuard
add-on működését, és frissítés után is megmarad.

### Vagy add meg a címet közvetlenül

Ha nem akarod publikálni a portot, vagy az AdGuard nem a Home Assistant alatt
fut, írd be a címet ennek az add-onnak az **AdGuard Home URL** opciójába. **Ez
nem kerülőmegoldás**, ugyanolyan támogatott út. Elfogadott formák:

| Amit beírsz | Mit jelent |
|---|---|
| `9000` vagy `:9000` | a Home Assistant hoszt 9000-es portja |
| `192.168.1.5:9000` | egy másik gép |
| `http://adguard.local:9000` | teljes URL |
| `https://adguard.example` | HTTPS (ehhez lásd az `adguard_verify_ssl` opciót) |

### Kell felhasználónév és jelszó?

Az AdGuard add-on ezt a portot alapértelmezésben **Home Assistant
bejelentkezéssel** védi. Ezért:

| AdGuard add-on `leave_front_door_open` | Mit adj meg ennek az add-onnak |
|---|---|
| `false` (alapértelmezés) | Egy **Home Assistant felhasználó** nevét és jelszavát |
| `true` | Üresen hagyhatod, vagy az AdGuard saját felhasználóját, ha van |

> **Tipp:** érdemes külön HA felhasználót létrehozni ehhez (például
> `adguard-log-viewer`), és nem a saját admin fiókodat használni.

---

## 3. Telepítés

1. **Beállítások → Kiegészítők → Kiegészítőtár → ⋮ → Tárolók**.
2. Add hozzá ennek a repónak az URL-jét.
3. Telepítsd az **AdGuard Log Viewer** add-ont.
4. A **Konfiguráció** fülön add meg a felhasználónevet és jelszót (lásd fent).
5. **Indítás**, majd **Megnyitás a webes felületen** — vagy az oldalsávból,
   ha bekapcsolod a *Megjelenítés az oldalsávban* kapcsolót.

Első indításkor az add-on visszamenőleg is beolvassa az AdGuard logját, a
megőrzési idő (`retention_days`) határáig. Ez pár percig tarthat; közben a
felület már használható, és az adatok folyamatosan jelennek meg.

---

## 4. Beállítások

| Opció | Alapértelmezés | Leírás |
|---|---|---|
| `adguard_url` | *(üres)* | Az a cím, amin az AdGuardot megnyitod. Üresen hagyva a Supervisortól kérdezi le — ehhez az AdGuard add-onnak publikálnia kell a `80/tcp` portot. Ha nem publikálja, írd ide a címet; elég egy önmagában álló port is (pl. `9000`). |
| `adguard_username` | *(üres)* | Home Assistant felhasználónév (lásd 2. pont). |
| `adguard_password` | *(üres)* | A hozzá tartozó jelszó. A HA maszkolja, az add-on soha nem logolja. |
| `adguard_verify_ssl` | `false` | Csak akkor kapcsold be, ha az AdGuard HTTPS-en, érvényes tanúsítvánnyal érhető el. |
| `adguard_slug` | *(üres)* | Csak ha az automatikus felderítés rossz add-ont találna (pl. `a0d7b954_adguard`). |
| `provider` | `auto` | `api` = AdGuard HTTP API (HA OS alatt egyedül ez működik), `file` = `querylog.json` közvetlen olvasása. |
| `querylog_path` | *(üres)* | Csak a `file` forráshoz. HA OS alatt hagyd üresen. |
| `poll_interval` | `10` | Hány másodpercenként kérje le az új rekordokat. |
| `ingest_batch_size` | `500` | Rekord/API hívás. |
| `max_pages_per_poll` | `20` | Egy lekérdezési kör felső korlátja. A régebbi előzményeket a következő körök hozzák be. |
| `ingest_enabled` | `true` | Kikapcsolva az importálás leáll, de a felület tovább használható. |
| `retention_days` | `30` | Hány napnyi előzményt tartson meg. `0` = korlátlan. A Settings oldalról is felülírható. |
| `log_level` | `info` | `debug` szinten az add-on a lekérdezett domaineket is logolhatja — csak hibakereséshez. |

A felület **Settings** oldalán módosítható, ami nem igényel újraindítást: nyelv,
téma, sűrűség, alapértelmezett időszak, oldalméret, megőrzési idő, importálás
ki/be. Az add-on options-ok ott csak olvashatóan jelennek meg.

---

## 5. Használat

### Keresés több feltétellel

A keresőmezőbe több kifejezést is beírhatsz — mindegyik **Enter**-rel kerül be
külön címkeként. Kettőnél több feltételnél megjelenik egy **ANY / ALL** kapcsoló:

* **ANY** — azok a kérések, amelyekben *legalább az egyik* szerepel
  (pl. `googl`, `youtube`, `googlevideo`);
* **ALL** — csak azok, amelyekben *mindegyik*.

A kereső melletti legördülőben választhatod ki, hogy mire keressen: domain,
kliens IP, eszköznév, válasz, szűrőszabály, vagy az összes mező.

### Advanced filter

Az **Advanced** gombbal tetszőleges mélységű AND/OR feltételfa építhető, például:

```
(domain contains "youtube" OR domain contains "googlevideo")
AND (person = "Péter" OR person = "Anna")
AND timestamp >= now-24h
```

A teljes szűrő a szerveren, SQL-ben fut le — a böngésző soha nem kap több adatot,
mint amit megjelenít.

### Mentett szűrők

A szűrősor **Save** gombja elmenti az aktuális szűrőt. A **Saved filters**
oldalon átnevezhető, szerkeszthető, törölhető, és egy kattintással aktiválható.

### Eszközök és személyek

* **Devices** — minden kliens IP, amit az AdGuard látott. Saját nevet adhatsz
  neki (ez felülírja az AdGuard nevét), és hozzárendelheted egy személyhez.
* **People** — egy személyhez több eszköz tartozhat. Utána egyetlen szűrővel
  látod az összes eszköze forgalmát, és több személy is kiválasztható egyszerre.

### Címkék és kategóriák

Minden domain automatikusan kap címkéket egy beépített szabálykészletből
(Google, YouTube, Advertising, Telemetry, IoT, News, …). A **Rules** oldalon
saját szabályokat is felvehetsz:

```
Név:        Munka
Feltételek: domain contains "intranet"
            OR domain endsWith "corp.local"
Címkék:     Work (category), Munkagép (tag)
```

A szabály mentése előtt a **Try it** mezőben kipróbálhatod egy konkrét domainen.
Szabálymódosítás után az érintett domainek a háttérben újraosztályozódnak; a
**Settings → Re-classify all domains** azonnal kényszeríti ezt.

Egy-egy domainhez kézzel is adhatsz címkét a domain részletező oldalán; a kézi
címkék a szabályok változásakor **megmaradnak**.

---

## 6. Hibakeresés

### Az add-on meg sem jelenik a tároló hozzáadása után

Ha a Kiegészítőtárban megjelenik a tároló, de üres, vagy az add-on hiányzik,
akkor a Supervisor **elutasította a `config.yaml`-t**, és ezt a felületen nem
írja ki. A pontos okot a Supervisor logja mondja meg:

**Beállítások → Rendszer → Naplók**, fent a legördülőben válaszd a
**Supervisor** naplót, és keress rá az add-on nevére. Egy elutasított
konfiguráció így néz ki:

```
Can't read config for ... : expected a non-empty string for docker image
```

Amit érdemes ellenőrizni:

1. **Frissítsd a tárolót.** Kiegészítőtár → ⋮ → *Frissítés*. A Supervisor
   gyorsítótárazza a tárolókat, ezért egy javítás push után nem jelenik meg
   azonnal. Parancssorból: `ha addons reload`.
2. **Architektúra.** Ez az add-on `aarch64` és `amd64` gépeken fut. Ha a
   Home Assistant `armv7` vagy `i386` (régi Raspberry Pi, 32 bites rendszer),
   nem fog látszani. Ellenőrzés: **Beállítások → Rendszer → Névjegy**.
3. **A tároló elérhető-e.** Privát GitHub repónál a Supervisor nem tudja
   letölteni; publikusnak kell lennie, vagy hitelesítés kell hozzá.

### „AdGuard Home is not reachable"

A **Settings** oldal megmondja, mit lát az add-on. A gyakori okok:

| Tünet | Ok | Megoldás |
|---|---|---|
| `The AdGuard Home address could not be worked out` | Az AdGuard add-on nem publikál hoszt portot a `80/tcp`-hez | 2. pont: állíts be portot, **vagy** add meg az `adguard_url`-t. A Settings oldal **How it was looked up** sora lépésről lépésre megmutatja, mit talált, és hogy a Supervisor milyen portokat jelent az AdGuard add-onra |
| `Cannot reach AdGuard Home at <cím>` | A cím megvan, de nem válaszol | Ellenőrizd, hogy az AdGuard fut-e, és hogy tényleg ezen a porton érhető el |
| `HTTP 401` vagy `403` | Hiányzó vagy rossz belépési adat | Adj meg érvényes **Home Assistant** felhasználót és jelszót |
| `returned text/html instead of JSON` | A kérést az nginx bejelentkeztető rétege fogta el | Ugyanaz: a felhasználónév/jelszó nem stimmel |
| `No AdGuard Home add-on was found` | A felderítés nem talált AdGuardot | Add meg kézzel az `adguard_url`-t |

### Nem jönnek új rekordok

* A **Settings** oldalon nézd meg a *Last poll* sort.
* Ellenőrizd, hogy az AdGuard Home-ban a query log be van-e kapcsolva — ha nincs,
  az add-on külön figyelmeztet.
* Az **Import new queries from AdGuard** kapcsoló ne legyen kikapcsolva.

### Élő frissítés nem működik

A felület Server-Sent Events-et használ. Ha a stream nem épül fel, az add-on
automatikusan 15 másodperces lekérdezésre vált — a *Live* jelző ilyenkor is zöld
marad, csak lassabban frissül.

### Az adatbázis nagy

A **Settings → Database** szekció mutatja a méretét. Csökkentsd a
`retention_days` értéket, majd futtasd a **Run cleanup now** gombot.

---

## 7. Adatvédelem

* A DNS előzmény **nem hagyja el a gépet**. Nincs telemetria, nincs külső
  analytics, nincs felhő, nincs külső AI API.
* Hálózati kapcsolat csak két cél felé megy: a Supervisor (`http://supervisor`)
  és az AdGuard add-on lokális címe.
* A kategória-listák a repóban vannak, offline — futásidőben semmit nem tölt le.
* Az add-on a lekérdezett domaineket `debug` szint alatt nem írja ki a logba.
* A felületet a Home Assistant saját felhasználókezelése védi (ingress). Ha
  publikálod a `8099/tcp` portot, azt a HA bejelentkezés **nem** védi.

---

## 8. Mentés és frissítés

* Minden adat az add-on `/data` könyvtárában van
  (`/data/adguard_log_viewer.db`), amit a **Home Assistant backup automatikusan
  visz**. Nagy adatbázisnál ez érezhetően növeli a mentés méretét — ilyenkor
  érdemes kisebb `retention_days` értéket választani.
* Frissítéskor az adatbázis séma automatikusan migrálódik; az importált
  rekordok, eszköznevek, személyek, címkék és mentett szűrők megmaradnak.
