# AdGuard Log Viewer — használati útmutató

DNS query log böngésző és elemző az AdGuard Home-hoz, Home Assistant add-onként.

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
3. A **Web interface** (`80/tcp`) sorba írj be egy szabad portot, például `3000`.
4. **Mentés**, majd az AdGuard Home add-on **újraindítása**.

Ez támogatott, dokumentált Home Assistant beállítás — nem módosítja az AdGuard
add-on működését, és frissítés után is megmarad.

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
| `adguard_url` | *(üres)* | Hagyd üresen: az add-on a Supervisoron keresztül megkeresi az AdGuard add-ont. Csak akkor töltsd ki, ha az AdGuard máshol fut (pl. `http://192.168.1.2:3000`). |
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

A felület **Settings** oldalán módosítható, ami nem igényel újraindítást: téma,
sűrűség, alapértelmezett időszak, oldalméret, megőrzési idő, importálás
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
| `Cannot reach AdGuard Home at http://172.30.32.1:3000` | Az AdGuard webes portja nincs publikálva | 2. pont: állíts be portot a `80/tcp`-hez, és indítsd újra az AdGuardot |
| `HTTP 401` vagy `403` | Hiányzó vagy rossz belépési adat | Adj meg érvényes **Home Assistant** felhasználót és jelszót |
| `returned text/html instead of JSON` | A kérést az nginx bejelentkeztető rétege fogta el | Ugyanaz: a felhasználónév/jelszó nem stimmel |
| `The AdGuard Home add-on could not be found` | A felderítés nem talált AdGuardot | Add meg kézzel az `adguard_url`-t |

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
