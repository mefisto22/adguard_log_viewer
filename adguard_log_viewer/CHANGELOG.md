# Changelog

## 0.1.5

**Az automatikus felderítés eddig soha nem működhetett.**

- A Home Assistant base image s6-overlay-t használ initként, és az s6 a
  konténer környezeti változóit **nem adja át** az általa indított
  folyamatnak — külön helyre teszi őket, és `with-contenv`-vel kell
  visszakérni. Emiatt az add-on soha nem látta a `SUPERVISOR_TOKEN`-t, így nem
  tudta megkérdezni a Supervisortól, hol van az AdGuard; és nem látta a `TZ`-t
  sem, így minden időbélyeg UTC szerint jelent meg. A belépési pont mostantól
  `with-contenv`-en keresztül indul, az `app.config` pedig tartalékként
  közvetlenül is olvassa az s6 környezetét.
- Az AdGuard mögötti nginx HTML hibaoldalait nem másoljuk többé nyersen a
  logba, csak a lényeget: `... returned HTTP 500 for /querylog (500 Internal
  Server Error)`.

## 0.1.4

Az AdGuard felderítése.

- **Nem találjuk ki a portot.** A `80/tcp` az AdGuard *konténer* oldali portja;
  a hoszt port a felhasználó választása, amire nincs értelmes alapérték.
  Korábban, ha a felderítés nem járt sikerrel, az add-on a
  `http://172.30.32.1:3000` címet találta ki — így minden hiba egy olyan portra
  mutatott, aminek semmi köze a beállításhoz. Mostantól ilyenkor azt mondja meg,
  mit nézett meg és mit talált.
- A Settings oldal **How it was looked up** sora lépésről lépésre mutatja a
  felderítést, és kiírja, milyen portokat jelent a Supervisor az AdGuard
  add-onra — így látszik, miért nem jött ki cím.
- Az **AdGuard Home URL** opció leírása átírva: a cím megadása ugyanolyan
  támogatott út, nem kerülőmegoldás. Egy önmagában álló port is elég
  (`9000` → a Home Assistant hoszt 9000-es portja), és `host:port`, illetve
  séma nélküli cím is elfogadott.
- A felderítés elfogad egyetlen egyéb publikált TCP portot is, ha a `80/tcp`
  nincs kiadva — ez AdGuard forkoknál számít.

## 0.1.3

Elrendezési javítások.

- **A kék sáv kilógott a kártya keretéből.** Egy hosszú, törhetetlen felirat —
  egy DoH upstream URL — szétfeszítette a sorát, a sor a rácsoszlopát, a sor
  szélességének 100%-ára méretezett sáv pedig 161 pixellel a kártyán kívülre
  került. A felirat mostantól három ponttal záródik, ahogy eddig is kellett
  volna.
- A táblázatok telefonméretben a kártyán belül görgethetők, nem lógnak ki.
- A kártyafejlécek keskeny képernyőn tördelnek.

## 0.1.2

Hibajavítások a felületen.

- **A mentett szűrő nem szűrt.** A Save gomb a keresőmezőbe írt kifejezésektől
  jelent meg, de azokat nem mentette el, így üres szűrő került az adatbázisba.
  A mentés mostantól a keresőkifejezéseket is tartalmazza, a backend pedig
  visszautasítja az üres szűrőt. A feltételszámláló a *tényleges* feltételeket
  számolja, így nem mutathat „Advanced (1)"-et olyan szűrőre, ami nem szűr.
- **Az eszközlista üres maradt a query log szűrősorában.** Az eszközök,
  személyek és címkék csak induláskor töltődtek be, friss telepítésnél pedig a
  felület hamarabb állt fel, mint hogy az ingest megtalálta volna az első
  klienst. Az alkalmazás most egyetlen élő kapcsolatot tart fenn, és frissíti
  ezeket a listákat, amikor új kliens vagy domain érkezik.
- **A legördülők magasabbak voltak a gomboknál.** Minden szűrősor-vezérlő
  közös, rögzített magasságot kapott.
- A Settings oldal külön mutatja az utolsó lekérdezést és az utolsó tényleges
  importot — korábban egy üres lekérdezés felülírta a statisztikát, így mindig
  „0 new record" látszott.

## 0.1.1

Csomagolási és ingest javítások.

- A `config.yaml` `image: null` kulcsa miatt a Supervisor elutasította a
  konfigurációt, így az add-on meg sem jelent a Kiegészítőtárban. A kulcs
  törölve; helyben épül az image, ahogy eddig is szándékozott.
- A `.gitignore` egy horgonyozatlan `data/` mintája kizárta a beépített
  kategorizáló szabálykészletet a repóból, így az image szabályok nélkül épült
  volna. A minta horgonyozva.
- A `map:` bejegyzés a mai, explicit `type` / `read_only` formára váltott.
- A fájl-provider nem vette észre a logrotációt, ha az új fájl ugyanarra az
  inode-ra került és a mérete is megegyezett. A rotációdetektálás most a már
  beolvasott tartalom ujjlenyomatát is ellenőrzi.
- Új csomagolási tesztek, és a CI mostantól elindítja a lefordított konténert.

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
