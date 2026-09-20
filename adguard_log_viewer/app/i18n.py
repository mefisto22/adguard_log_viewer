"""Translating the messages the backend sends to the browser.

Most of the interface is translated in the frontend, where the text lives in a
dictionary. A handful of strings are produced here instead — validation errors,
"not found" replies, and the diagnostics explaining how (and whether) AdGuard
Home was located. Those reach the user through the same screens, so they have
to speak the same language as everything around them.

The mechanism is deliberately small. :class:`Message` *is* a ``str`` holding the
English text, so logging, tests and any code that never asks about language keep
working unchanged; it additionally remembers the template it was built from, and
:meth:`Message.localized` re-renders that template from the catalogue. The
English text doubles as the lookup key, the way gettext uses the English string
as its msgid — a missing translation therefore degrades to English rather than
to a bare key.

The language for the current request is held in a context variable, set by the
middleware in :mod:`app.main`. Context variables are per-task, and each request
is its own task, so concurrent requests in different languages do not interfere.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

DEFAULT_LANGUAGE = "en"

#: Languages the app speaks. Keep in step with the frontend dictionaries and
#: with ``translations/*.yaml``, which localise the app's own options page.
LANGUAGES: tuple[str, ...] = ("en", "hu")

_current_language: ContextVar[str] = ContextVar("language", default=DEFAULT_LANGUAGE)


def normalize_language(value: str | None) -> str | None:
    """Map a language tag onto a language we have. ``hu-HU`` -> ``hu``."""
    if not value:
        return None
    base = value.strip().lower().split(",")[0].split(";")[0].split("-")[0].split("_")[0]
    return base if base in LANGUAGES else None


def resolve_language(header: str | None = None, preference: str | None = None) -> str:
    """Work out the language for a request.

    The browser's ``Accept-Language`` wins: the frontend sets it to the language
    it is actually rendering, which already accounts for the user's own choice
    on the Settings page. A stored preference covers other clients, and English
    is the last resort.
    """
    if header:
        # The header is a weighted list; the frontend sends a single tag, and
        # taking the first entry is the right reading for a browser's own list
        # too, which is ordered by preference.
        for part in header.split(","):
            language = normalize_language(part)
            if language:
                return language
    if preference and preference != "auto":
        language = normalize_language(preference)
        if language:
            return language
    return DEFAULT_LANGUAGE


def current_language() -> str:
    return _current_language.get()


def set_current_language(language: str) -> Any:
    """Set the language for this task. Returns a token for :func:`reset`."""
    return _current_language.set(language if language in LANGUAGES else DEFAULT_LANGUAGE)


def reset_current_language(token: Any) -> None:
    _current_language.reset(token)


class LocalizedText(str):
    """An English string that also knows how to say itself in another language.

    It is a ``str`` so logging, tests and every caller that does not care about
    language keep working unchanged; :func:`localize` asks it for a translation
    at the point where a response is built.
    """

    __slots__ = ()

    def localized(self, language: str | None = None) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


class Message(LocalizedText):
    """An English string that can also say itself in another language.

    Built from a template and its parameters so the translation can put them in
    a different order::

        Message("The '{name}' app is not running (state: {state}).",
                name="AdGuard Home", state="stopped")
    """

    __slots__ = ("msgid", "params")

    msgid: str
    params: Mapping[str, Any]

    def __new__(cls, msgid: str, /, **params: Any) -> Message:
        text = msgid.format(**params) if params else msgid
        message = super().__new__(cls, text)
        message.msgid = msgid
        message.params = params
        return message

    def localized(self, language: str | None = None) -> str:
        language = language or current_language()
        template = CATALOG.get(language, {}).get(self.msgid)
        if template is None:
            return str(self)
        if not self.params:
            return template
        # A parameter may itself be a Message — the AdGuard diagnostics build a
        # sentence around an explanation that is a message in its own right.
        params = {
            key: value.localized(language) if isinstance(value, LocalizedText) else value
            for key, value in self.params.items()
        }
        try:
            return template.format(**params)
        except (IndexError, KeyError):
            # A translation with a placeholder the message does not supply.
            # Showing the English text beats raising while rendering an error.
            return str(self)


class JoinedMessage(LocalizedText):
    """Several messages read as one line, each still translated on its own.

    Used where separate findings are presented together — the AdGuard warnings
    shown as a single provider status, for instance. Joining the English text
    first would freeze it in English.
    """

    __slots__ = ("parts", "separator")

    parts: tuple[Any, ...]
    separator: str

    def __new__(cls, parts: Any, separator: str = " ") -> JoinedMessage:
        items = tuple(parts)
        joined = super().__new__(cls, separator.join(str(part) for part in items))
        joined.parts = items
        joined.separator = separator
        return joined

    def localized(self, language: str | None = None) -> str:
        return self.separator.join(str(localize(part, language)) for part in self.parts)


def detail_of(err: BaseException) -> str:
    """The message carried by a raised error.

    Code raises ``ValueError(Message(...))`` so the text can be translated later.
    ``str(err)`` would flatten that back to plain English, so take the argument
    itself when there is one — a :class:`Message` is a ``str``, and everything
    downstream treats it as one.
    """
    if err.args and isinstance(err.args[0], LocalizedText):
        return err.args[0]
    return str(err)


def localize(value: Any, language: str | None = None) -> Any:
    """Render *value* in *language* when it knows how."""
    if isinstance(value, LocalizedText):
        return value.localized(language)
    return value


def localize_all(values: list[Any], language: str | None = None) -> list[Any]:
    return [localize(value, language) for value in values]


#: English msgid -> translation. Only Hungarian for now; adding a language means
#: adding a key here and to ``LANGUAGES``.
CATALOG: dict[str, dict[str, str]] = {
    "hu": {
        # --- generic API replies ------------------------------------------
        "The application is still starting": "Az alkalmazás még indul",
        "The ingest loop is not running": "A begyűjtő folyamat nem fut",
        # --- tags ----------------------------------------------------------
        "A tag needs a name": "A címkének kell egy név",
        "A tag with that name already exists": "Már létezik ilyen nevű címke",
        "Tag not found or nothing to change": "A címke nem található, vagy nincs mit módosítani",
        "Tag not found": "A címke nem található",
        "kind must be one of {kinds}": "a típus csak ez lehet: {kinds}",
        "A tag named {name} already exists": "Már létezik {name} nevű címke",
        "A category named {name} already exists": "Már létezik {name} nevű kategória",
        "Built-in tags cannot be deleted. Disable the rule that applies it instead.": (
            "A beépített címkék nem törölhetők. Tiltsd le inkább az őket alkalmazó szabályt."
        ),
        # --- domains -------------------------------------------------------
        "Domain not found": "A domain nem található",
        # --- rules ---------------------------------------------------------
        "A rule with that name already exists": "Már létezik ilyen nevű szabály",
        "Rule not found": "A szabály nem található",
        "A domain is required": "Meg kell adni egy domaint",
        "The rule needs a name, at least one condition and at least one tag": (
            "A szabályhoz név, legalább egy feltétel és legalább egy címke kell"
        ),
        "A rule needs a name, at least one condition and at least one tag": (
            "A szabályhoz név, legalább egy feltétel és legalább egy címke kell"
        ),
        "The categorisation engine is not ready": "A besoroló motor még nem áll készen",
        # --- queries and saved filters -------------------------------------
        "Saved filter not found": "A mentett szűrő nem található",
        "Query not found": "A lekérdezés nem található",
        "A saved filter needs a name": "A mentett szűrőnek kell egy név",
        "A saved filter named {name} already exists": "Már létezik {name} nevű mentett szűrő",
        (
            "A saved filter needs at least one condition. An empty filter matches every "
            "query, which is the same as having no filter at all."
        ): (
            "A mentett szűrőhöz legalább egy feltétel kell. Az üres szűrő minden "
            "lekérdezésre illeszkedik, ami ugyanaz, mintha nem lenne szűrő."
        ),
        "Unknown dashboard part: {part}": "Ismeretlen áttekintő rész: {part}",
        # --- devices and people ---------------------------------------------
        "Device not found": "Az eszköz nem található",
        "Device not found or nothing to change": (
            "Az eszköz nem található, vagy nincs mit módosítani"
        ),
        "A person needs a name": "A személynek kell egy név",
        "A person with that name already exists": "Már létezik ilyen nevű személy",
        "Person not found or nothing to change": (
            "A személy nem található, vagy nincs mit módosítani"
        ),
        "Person not found": "A személy nem található",
        # --- filter validation ----------------------------------------------
        "Each filter node must be an object": "Minden szűrőelemnek objektumnak kell lennie",
        "Filter is nested deeper than {max} levels": (
            "A szűrő mélyebben ágazik {max} szintnél"
        ),
        "Filter has more than {max} nodes": "A szűrő több mint {max} elemet tartalmaz",
        "Unknown group operator {op}": "Ismeretlen csoportművelet: {op}",
        "Group {op} needs a 'children' array": "A(z) {op} csoporthoz 'children' tömb kell",
        "'not' takes exactly one child": "A 'not' pontosan egy gyermeket vár",
        "A condition needs a 'field'": "A feltételhez 'field' mező kell",
        "Unknown filter field {field}": "Ismeretlen szűrőmező: {field}",
        "Operator {operator} is not valid for field {field}; allowed: {allowed}": (
            "A(z) {operator} művelet nem használható a(z) {field} mezőn; "
            "megengedett: {allowed}"
        ),
        "Operator {operator} needs a non-empty 'values' array": (
            "A(z) {operator} művelethez nem üres 'values' tömb kell"
        ),
        "A list condition may not hold more than 500 values": (
            "Egy listafeltétel legfeljebb 500 értéket tartalmazhat"
        ),
        "Condition on {field} needs a 'value'": "A(z) {field} feltételhez 'value' érték kell",
        "A regular expression may not be longer than {max} characters": (
            "A reguláris kifejezés nem lehet hosszabb {max} karakternél"
        ),
        "A list condition needs at least one value": (
            "Egy listafeltételhez legalább egy érték kell"
        ),
        "Operator {operator} cannot be applied to a text field": (
            "A(z) {operator} művelet nem alkalmazható szöveges mezőre"
        ),
        "Operator {operator} cannot be applied to a numeric field": (
            "A(z) {operator} művelet nem alkalmazható numerikus mezőre"
        ),
        "Operator {operator} cannot be applied to a time field": (
            "A(z) {operator} művelet nem alkalmazható időmezőre"
        ),
        "{field} expects a number, got {value}": "{field} számot vár, de ezt kapta: {value}",
        "Cannot interpret {value} as a point in time": (
            "A(z) {value} nem értelmezhető időpontként"
        ),
        "Unknown result kind": "Ismeretlen eredménytípus",
        "Field {field} cannot be filtered on": "A(z) {field} mezőre nem lehet szűrni",
        "The query was still running after {seconds} seconds and was "
        "stopped. Narrow the time range, or simplify the filter — a regular "
        "expression in particular cannot use an index.": (
            "A lekérdezés {seconds} másodperc után is futott, ezért leállt. Szűkítsd az "
            "időtartományt, vagy egyszerűsítsd a szűrőt — reguláris kifejezés esetén "
            "különösen, mert az nem tud indexet használni."
        ),
        # --- settings validation ---------------------------------------------
        "{key} is not a settable option": "A(z) {key} beállítás nem módosítható",
        "language must be one of {allowed}": "a nyelv csak ez lehet: {allowed}",
        "theme must be one of {allowed}": "a téma csak ez lehet: {allowed}",
        "density must be one of {allowed}": "a sűrűség csak ez lehet: {allowed}",
        "page_size must be a number": "a page_size csak szám lehet",
        "retention_days must be a number": "a retention_days csak szám lehet",
        "retention_days cannot be negative": "a retention_days nem lehet negatív",
        "{key} must be a list": "a(z) {key} csak lista lehet",
        "That name is already taken": "Ez a név már foglalt",
        "Not found": "Nem található",
        # --- finding the AdGuard app --------------------------------------
        "Using the address from the app options: {url}": (
            "Az alkalmazás beállításaiban megadott cím használata: {url}"
        ),
        "No Supervisor token, so the AdGuard app cannot be looked up.": (
            "Nincs Supervisor token, így az AdGuard alkalmazás nem kereshető meg."
        ),
        "This app has no Supervisor token, so it cannot look the AdGuard "
        "app up. Set the 'AdGuard Home URL' option explicitly.": (
            "Ennek az alkalmazásnak nincs Supervisor tokenje, így nem tudja megkeresni az "
            "AdGuard alkalmazást. Add meg kézzel az „AdGuard Home URL” beállítást."
        ),
        "App slug from the options: {slug}": (
            "A beállításokban megadott alkalmazásazonosító: {slug}"
        ),
        "Supervisor discovery announced AdGuard as '{slug}'": (
            "A Supervisor felderítése {slug} néven jelentette az AdGuardot"
        ),
        "Supervisor discovery returned nothing; falling back to known slugs.": (
            "A Supervisor felderítése nem adott vissza semmit; ismert azonosítók "
            "próbálása következik."
        ),
        "No app installed under: {slugs}": (
            "Nincs telepített alkalmazás ezekkel az azonosítókkal: {slugs}"
        ),
        "No AdGuard Home app was found through the Supervisor. Set the "
        "'AdGuard Home URL' option to the address you use to open AdGuard.": (
            "A Supervisoron keresztül nem található AdGuard Home alkalmazás. Állítsd be az "
            "„AdGuard Home URL” beállítást arra a címre, amelyen az AdGuardot eléred."
        ),
        "'{name}' ({version}): {explanation}": "„{name}” ({version}): {explanation}",
        "unknown version": "ismeretlen verzió",
        "the Supervisor reported no port mapping for this app": (
            "a Supervisor nem jelentett porthozzárendelést ehhez az alkalmazáshoz"
        ),
        "{container_port} is published on host port {port}": (
            "a(z) {container_port} a gazdagép {port} portján érhető el"
        ),
        "{container_port} is the only published TCP port, using host port {port}": (
            "a(z) {container_port} az egyetlen közzétett TCP port, a gazdagép {port} "
            "portját használjuk"
        ),
        "several TCP ports are published ({ports}) and none of them is {container_port}": (
            "több TCP port is közzé van téve ({ports}), és egyik sem a(z) {container_port}"
        ),
        "{container_port} has no host port assigned (the Supervisor reported {network})": (
            "a(z) {container_port} porthoz nincs gazdagépport rendelve "
            "(a Supervisor ezt jelentette: {network})"
        ),
        "The '{name}' app does not publish its web interface port, so its "
        "address cannot be worked out: {explanation}. Either open that app's "
        "Configuration page and assign a host port to {container_port} under "
        "Network, or set this app's 'AdGuard Home URL' option to the address "
        "you already use.": (
            "A(z) „{name}” alkalmazás nem teszi közzé a webes felületének portját, így a "
            "címe nem állapítható meg: {explanation}. Nyisd meg annak az alkalmazásnak a "
            "Konfiguráció lapját, és rendelj gazdagépportot a(z) {container_port} "
            "porthoz a Network résznél, vagy add meg ennek az alkalmazásnak az „AdGuard "
            "Home URL” beállításában azt a címet, amit amúgy is használsz."
        ),
        "The '{name}' app is not running (state: {state}).": (
            "A(z) „{name}” alkalmazás nem fut (állapot: {state})."
        ),
        # --- talking to AdGuard Home -----------------------------------------
        "The AdGuard Home address could not be worked out.": (
            "Az AdGuard Home címe nem volt megállapítható."
        ),
        " The AdGuard Home app protects its web port with Home Assistant "
        "login by default — set a Home Assistant username and password in "
        "this app's options.": (
            " Az AdGuard Home alkalmazás alapértelmezés szerint Home Assistant "
            "bejelentkezéssel védi a webes portját — add meg a Home Assistant "
            "felhasználónevet és jelszót ennek az alkalmazásnak a beállításai között."
        ),
        "Cannot reach AdGuard Home at {url}: {error}": (
            "Az AdGuard Home nem érhető el itt: {url} — {error}"
        ),
        "AdGuard Home returned HTTP {status} for {path}{detail}": (
            "Az AdGuard Home HTTP {status} választ adott erre: {path}{detail}"
        ),
        "AdGuard Home returned {content_type} instead of JSON for {path}; "
        "check the credentials": (
            "Az AdGuard Home JSON helyett ezt adta vissza a(z) {path} kérésre: "
            "{content_type}; ellenőrizd a belépési adatokat"
        ),
        "an unknown content type": "ismeretlen tartalomtípus",
        "Malformed JSON from AdGuard Home for {path}": (
            "Hibás JSON érkezett az AdGuard Home-tól erre: {path}"
        ),
        "Connected to AdGuard Home": "Kapcsolódva az AdGuard Home-hoz",
        "Connected to AdGuard Home {version}": (
            "Kapcsolódva az AdGuard Home {version} verziójához"
        ),
        "AdGuard Home reports that its DNS server is not running.": (
            "Az AdGuard Home jelentése szerint a DNS-kiszolgálója nem fut."
        ),
        "The query log is disabled in AdGuard Home; no new records will arrive.": (
            "A lekérdezési napló ki van kapcsolva az AdGuard Home-ban; nem érkezik új "
            "bejegyzés."
        ),
        "AdGuard Home anonymises client IP addresses, so per-device "
        "attribution will be incomplete.": (
            "Az AdGuard Home anonimizálja a kliensek IP-címeit, így az eszközönkénti "
            "hozzárendelés hiányos lesz."
        ),
        # --- the file provider -------------------------------------------------
        "{path} does not exist inside this container. On Home "
        "Assistant OS an app cannot read another app's data "
        "directory — use the AdGuard API provider instead.": (
            "A(z) {path} nem létezik ezen a konténeren belül. Home Assistant OS alatt "
            "egy alkalmazás nem olvashatja egy másik alkalmazás adatkönyvtárát — használd "
            "helyette az AdGuard API forrást."
        ),
        "{path} exists but is not readable by this app.": (
            "A(z) {path} létezik, de ez az alkalmazás nem tudja olvasni."
        ),
        "Tailing {path}": "A(z) {path} követése",
    },
}
