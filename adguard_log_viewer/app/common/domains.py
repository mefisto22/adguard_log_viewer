"""Domain name helpers.

``registrable_domain`` approximates the public-suffix + 1 label rule with a
bundled list of the multi-label suffixes that actually show up in home DNS
traffic. A full Public Suffix List would mean a runtime download, which this
app deliberately avoids (see ARCHITECTURE.md, security section). The result
is only used for grouping and display, never for a security decision.
"""

from __future__ import annotations

#: Suffixes made of more than one label. Used to decide where the registrable
#: domain starts. Keep sorted by label count, longest first.
MULTI_LABEL_SUFFIXES: frozenset[str] = frozenset(
    {
        # generic second levels
        "co.uk", "org.uk", "me.uk", "ltd.uk", "plc.uk", "net.uk", "sch.uk", "ac.uk", "gov.uk",
        "com.au", "net.au", "org.au", "edu.au", "gov.au", "id.au", "asn.au",
        "co.nz", "net.nz", "org.nz", "govt.nz", "ac.nz", "school.nz",
        "co.za", "org.za", "net.za", "web.za", "gov.za", "ac.za",
        "com.br", "net.br", "org.br", "gov.br", "edu.br",
        "com.mx", "org.mx", "net.mx", "gob.mx", "edu.mx",
        "com.ar", "net.ar", "org.ar", "gob.ar", "edu.ar",
        "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp", "ad.jp", "ed.jp", "gr.jp", "lg.jp",
        "co.kr", "or.kr", "ne.kr", "go.kr", "re.kr", "pe.kr",
        "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn",
        "com.tw", "net.tw", "org.tw", "gov.tw", "edu.tw",
        "com.hk", "net.hk", "org.hk", "gov.hk", "edu.hk", "idv.hk",
        "com.sg", "net.sg", "org.sg", "gov.sg", "edu.sg",
        "com.tr", "net.tr", "org.tr", "gov.tr", "edu.tr",
        "com.ua", "net.ua", "org.ua", "gov.ua", "edu.ua", "in.ua", "kiev.ua",
        "com.pl", "net.pl", "org.pl", "gov.pl", "edu.pl", "waw.pl",
        "com.ru", "net.ru", "org.ru", "edu.ru", "gov.ru",
        "co.in", "net.in", "org.in", "gen.in", "firm.in", "gov.in", "ac.in", "edu.in",
        "com.my", "net.my", "org.my", "gov.my", "edu.my",
        "com.ph", "net.ph", "org.ph", "gov.ph", "edu.ph",
        "com.vn", "net.vn", "org.vn", "gov.vn", "edu.vn",
        "co.id", "web.id", "or.id", "go.id", "ac.id", "sch.id",
        "co.il", "org.il", "net.il", "ac.il", "gov.il",
        "com.es", "org.es", "nom.es", "gob.es", "edu.es",
        "com.pt", "org.pt", "gov.pt", "edu.pt",
        "com.gr", "net.gr", "org.gr", "gov.gr", "edu.gr",
        "com.ro", "org.ro", "store.ro",
        "co.hu", "info.hu", "org.hu", "priv.hu", "sport.hu", "tm.hu", "2000.hu",
        "co.at", "or.at", "ac.at", "gv.at",
        "co.th", "in.th", "ac.th", "go.th", "or.th", "net.th",
        "com.eg", "com.sa", "com.ng", "com.pk", "com.bd", "com.co", "com.pe",
        "com.uy", "com.ve", "com.ec", "com.do", "com.gt", "com.bo",
        # platform suffixes worth grouping on their own
        "github.io", "gitlab.io", "pages.dev", "workers.dev", "web.app",
        "firebaseapp.com", "azurewebsites.net", "cloudfront.net", "herokuapp.com",
        "s3.amazonaws.com", "blob.core.windows.net", "akamaized.net", "akamai.net",
        "cdn.cloudflare.net", "b-cdn.net", "fastly.net", "edgekey.net", "edgesuite.net",
    }
)


def normalize_domain(name: str | None) -> str:
    """Lower-case, strip the trailing root dot and any surrounding whitespace.

    Returns an empty string for anything unusable.
    """
    if not name:
        return ""
    value = name.strip().strip(".").lower()
    if not value:
        return ""
    # Punycode stays as-is; it is what AdGuard reports and what matching uses.
    return value


def labels(domain: str) -> list[str]:
    normalized = normalize_domain(domain)
    return normalized.split(".") if normalized else []


def registrable_domain(domain: str) -> str:
    """Return the "registrable" part of *domain* (roughly eTLD+1).

    ``www.news.bbc.co.uk`` -> ``bbc.co.uk``; ``r1---sn-x.googlevideo.com`` ->
    ``googlevideo.com``; a bare label or an IP-looking name is returned as-is.
    """
    parts = labels(domain)
    if len(parts) < 2:
        return ".".join(parts)

    # Try the longest candidate suffix first (max 3 labels in the bundled list).
    for size in (3, 2):
        if len(parts) > size:
            candidate = ".".join(parts[-size:])
            if candidate in MULTI_LABEL_SUFFIXES:
                return ".".join(parts[-(size + 1) :])
    return ".".join(parts[-2:])


def parent_domains(domain: str) -> list[str]:
    """All suffixes of *domain* from the most specific to the least.

    ``a.b.example.com`` -> ``[a.b.example.com, b.example.com, example.com, com]``
    """
    parts = labels(domain)
    return [".".join(parts[i:]) for i in range(len(parts))]


def is_subdomain_of(domain: str, suffix: str) -> bool:
    """True when *domain* equals *suffix* or is a subdomain of it."""
    domain = normalize_domain(domain)
    suffix = normalize_domain(suffix)
    if not domain or not suffix:
        return False
    return domain == suffix or domain.endswith("." + suffix)
