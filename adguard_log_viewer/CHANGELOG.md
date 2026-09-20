# Changelog

## 0.2.2

**Two links that pointed somewhere else.** *(Magyarul lentebb.)*

- The "open the … page" link on the app card in Home Assistant led to a
  different owner and repository than this project's own. `config.yaml` and
  `build.yaml` now carry the real address, the one `repository.yaml` and the git
  remote already had.
- Renaming "add-on" to "app" in 0.2.1 rewrote a URL along with the prose, so the
  Home Assistant developer-documentation reference in `ARCHITECTURE.md` pointed
  at a path that does not exist. Restored.
- Both are now tested: the project URLs are checked against the remote this was
  cloned from, every relative link and heading anchor in the documents is
  resolved, and a URL containing an accented character — the fingerprint of a
  search-and-replace that reached inside a link — fails the build.

---

**Két link, ami máshová mutatott.**

- A Home Assistant alkalmazáskártyáján a „nyissa meg a(z) … oldalát" link egy
  másik tulajdonoshoz és másik tárolóhoz vezetett. A `config.yaml` és a
  `build.yaml` mostantól a valódi címet tartalmazza — ugyanazt, ami a
  `repository.yaml`-ban és a git remote-ban eddig is szerepelt.
- A 0.2.1-ben az „add-on” → „alkalmazás” átnevezés a szöveggel együtt egy URL-t
  is átírt, így az `ARCHITECTURE.md`-ben a Home Assistant fejlesztői
  dokumentációjára mutató hivatkozás nem létező útvonalra vitt. Javítva.
- Mindkettőre van már teszt: a projekt URL-jeit a klónozás forrásához
  hasonlítjuk, a dokumentumok minden relatív linkjét és címsor-horgonyát
  feloldjuk, és az ékezetes karaktert tartalmazó URL — ami egy linkbe belenyúló
  csere árulkodó jele — megbuktatja a buildet.

## 0.2.1

**"Add-on" is now "app".** *(Magyarul lentebb.)*

Home Assistant renamed add-ons to apps, so the wording here follows: the
interface, both READMEs, the documentation, the option descriptions and the
messages the backend produces all say "app" now — "alkalmazás" in Hungarian.
The documented menu paths follow suit: **Settings → Apps → Install app → ⋮ →
Repositories**.

Nothing that a machine reads changed, because Home Assistant did not rename any
of it: the Supervisor still serves `/addons/<slug>/info`, `config.yaml` still
takes `addon_config`, `all_addon_configs` and `hassio_role`, the CLI is still
`ha addons`, and this app's slug is unchanged. Upgrading needs nothing from you.
The one identifier that did move is the image label `io.hass.type`, now `app`
as Home Assistant's own documentation writes it; the Supervisor never reads it.

---

**Az „add-on” mostantól „alkalmazás”.**

A Home Assistant átnevezte az add-onokat alkalmazásra, így itt is ez a szóhasználat:
a felület, mindkét README, a dokumentáció, az opciók leírásai és a backend üzenetei
is alkalmazást írnak. A dokumentált menüutak is ehhez igazodnak:
**Beállítások → Alkalmazások → Alkalmazás telepítése → ⋮ → Tárolók**.

Amit gép olvas, abból semmi nem változott, mert a Home Assistant sem nevezte át:
a Supervisor továbbra is a `/addons/<slug>/info` végpontot szolgálja ki, a
`config.yaml` továbbra is `addon_config`, `all_addon_configs` és `hassio_role`
kulcsokat vár, a parancssor továbbra is `ha addons`, és ennek az alkalmazásnak az
azonosítója is ugyanaz maradt. A frissítés semmilyen teendőt nem igényel.
Az egyetlen azonosító, ami tényleg változott, az `io.hass.type` image-címke,
ami mostantól `app`, ahogy a Home Assistant dokumentációja is írja; ezt a
Supervisor soha nem olvassa.

## 0.2.0

**Hungarian and English, following Home Assistant.** *(Magyarul lentebb.)*

- The web interface is now translated. It reads the language from the Home
  Assistant frontend around it — under ingress the page is same-origin, so the
  `lang` attribute of the parent document is readable, and that reflects the
  language chosen in the user's profile rather than just the system default.
  Outside Home Assistant it falls back to the browser's language, then English.
- The app's Configuration page was already translated through
  `translations/en.yaml` and `translations/hu.yaml`; a packaging test now keeps
  those files in step with the option schema, so a new option cannot ship with
  an untranslated label.
- Messages produced by the backend — validation errors, "not found" replies and
  the diagnostics about reaching AdGuard Home — are translated too. Each request
  carries an `Accept-Language` header and the reply follows it.
- Dates, numbers and relative times use the same language, so a Hungarian page
  no longer mixes Hungarian labels with `09/19/2026` timestamps.
- Settings → Appearance → Language overrides the choice per user:
  *Follow Home Assistant*, *English* or *Magyar*.
- README.md and DOCS.md are bilingual, English first.

---

**Magyar és angol, a Home Assistantot követve.**

- A webes felület mostantól fordítva van. A nyelvet a körülötte lévő Home
  Assistant felülettől veszi — ingress alatt az oldal azonos origin-ről szolgál
  ki, így a szülő dokumentum `lang` attribútuma olvasható, az pedig a
  felhasználó profiljában választott nyelvet tükrözi, nem csak a rendszerét.
  Home Assistanton kívül a böngésző nyelvére, majd az angolra esik vissza.
- Az alkalmazás Konfiguráció lapja eddig is fordítva volt a `translations/en.yaml`
  és `translations/hu.yaml` fájlokból; mostantól egy csomagolási teszt tartja
  szinkronban ezeket az opciósémával, így új opció nem kerülhet ki lefordítatlan
  felirattal.
- A backend üzenetei — validációs hibák, „nem található" válaszok és az AdGuard
  elérésével kapcsolatos diagnosztika — szintén fordítottak. Minden kérés visz
  egy `Accept-Language` fejlécet, a válasz ehhez igazodik.
- A dátumok, számok és relatív időpontok is ezt a nyelvet követik, így egy magyar
  oldalon nem keverednek a feliratok `09/19/2026` alakú időbélyegekkel.
- A Settings → Megjelenés → Nyelv felhasználónként felülírja a választást:
  *Home Assistant szerint*, *English* vagy *Magyar*.
- A README.md és a DOCS.md két nyelvű, angollal kezdve.

## 0.1.5

**Az automatikus felderítés eddig soha nem működhetett.**

- A Home Assistant base image s6-overlay-t használ initként, és az s6 a
  konténer környezeti változóit **nem adja át** az általa indított
  folyamatnak — külön helyre teszi őket, és `with-contenv`-vel kell
  visszakérni. Emiatt az alkalmazás soha nem látta a `SUPERVISOR_TOKEN`-t, így nem
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
  Korábban, ha a felderítés nem járt sikerrel, az alkalmazás a
  `http://172.30.32.1:3000` címet találta ki — így minden hiba egy olyan portra
  mutatott, aminek semmi köze a beállításhoz. Mostantól ilyenkor azt mondja meg,
  mit nézett meg és mit talált.
- A Settings oldal **How it was looked up** sora lépésről lépésre mutatja a
  felderítést, és kiírja, milyen portokat jelent a Supervisor az AdGuard
  alkalmazásra — így látszik, miért nem jött ki cím.
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
  konfigurációt, így az alkalmazás meg sem jelent a telepíthető alkalmazások között. A kulcs
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
  alkalmazás's address and port discovered through the Supervisor at runtime.
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
