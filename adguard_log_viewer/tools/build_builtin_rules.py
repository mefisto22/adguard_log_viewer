#!/usr/bin/env python3
"""Generate ``app/categorization/data/builtin_rules.json``.

The built-in rule set is kept here in a compact, reviewable form and compiled
into the JSON the engine loads. Run after editing:

    python tools/build_builtin_rules.py

Everything is bundled with the app — no list is ever downloaded at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "categorization" / "data" / "builtin_rules.json"

# --- palette ---------------------------------------------------------------

CATEGORY_COLORS: dict[str, str] = {
    "Search": "#4285f4",
    "Video": "#e53935",
    "Streaming": "#8e24aa",
    "Music": "#1db954",
    "Social": "#1877f2",
    "Messaging": "#25d366",
    "Advertising": "#f57c00",
    "Analytics": "#fb8c00",
    "Tracking": "#d84315",
    "Telemetry": "#6d4c41",
    "Shopping": "#00897b",
    "News": "#3949ab",
    "Gaming": "#7b1fa2",
    "Cloud": "#0288d1",
    "CDN": "#0097a7",
    "Software Update": "#546e7a",
    "AI": "#00acc1",
    "Work": "#5e35b1",
    "Developer": "#455a64",
    "Finance": "#2e7d32",
    "Adult": "#c2185b",
    "Malware": "#b71c1c",
    "IoT": "#00796b",
    "OS Service": "#616161",
    "Email": "#1565c0",
    "File Sharing": "#795548",
    "Security": "#283593",
    "Travel": "#00838f",
    "Food": "#ef6c00",
    "Sports": "#2e7d32",
    "Education": "#4527a0",
    "Weather": "#0277bd",
    "Health": "#ad1457",
    "Government": "#37474f",
}

TAG_COLORS: dict[str, str] = {
    "Google": "#4285f4",
    "YouTube": "#ff0000",
    "Meta": "#0866ff",
    "Apple": "#555555",
    "Microsoft": "#00a4ef",
    "Amazon": "#ff9900",
    "Netflix": "#e50914",
    "Spotify": "#1db954",
    "TikTok": "#010101",
    "Discord": "#5865f2",
    "Steam": "#171a21",
    "OpenAI": "#10a37f",
    "Anthropic": "#d97757",
    "Cloudflare": "#f38020",
    "Home Assistant": "#41bdf5",
}

# --- rules -----------------------------------------------------------------
#
# (name, priority, tags, categories, suffixes, extra_conditions)
#
# `suffixes` become `domain suffix <value>` conditions, which match the domain
# itself and every subdomain. `extra_conditions` are raw (operator, value)
# pairs for the cases a suffix cannot express.

Rule = tuple[str, int, list[str], list[str], list[str], list[tuple[str, str]]]

RULES: list[Rule] = [
    # -- Google ------------------------------------------------------------
    ("YouTube", 10, ["Google", "YouTube"], ["Video", "Streaming"],
     ["youtube.com", "youtu.be", "ytimg.com", "googlevideo.com", "youtube-nocookie.com",
      "yt3.ggpht.com", "ytimg.l.google.com", "youtubei.googleapis.com", "youtubekids.com"],
     [("contains", "googlevideo"), ("contains", "youtube")]),
    ("Google Search", 20, ["Google"], ["Search"],
     ["google.com", "google.hu", "google.co.uk", "google.de", "google.at", "google.sk",
      "googleapis.com", "gstatic.com", "googleusercontent.com", "googletagmanager.com"],
     [("regex", r"^www\.google\.[a-z.]{2,6}$")]),
    ("Google Ads", 15, ["Google"], ["Advertising", "Tracking"],
     ["doubleclick.net", "googlesyndication.com", "googleadservices.com", "admob.com",
      "google-analytics.com", "googletagservices.com", "2mdn.net", "adservice.google.com"],
     []),
    ("Google Services", 30, ["Google"], ["Cloud"],
     ["gmail.com", "googlemail.com", "google-play.com", "play.google.com", "gvt1.com",
      "gvt2.com", "gvt3.com", "ggpht.com", "googlezip.net", "withgoogle.com",
      "firebaseio.com", "firebaseinstallations.googleapis.com", "crashlytics.com",
      "google.co", "chromium.org", "chrome.com", "googledomains.com"],
     []),
    ("Google Drive & Docs", 30, ["Google"], ["Work", "Cloud"],
     ["drive.google.com", "docs.google.com", "googledrive.com", "gsuite.google.com"], []),
    ("Android", 35, ["Google"], ["OS Service", "Software Update"],
     ["android.com", "android.clients.google.com", "dl.google.com",
      "connectivitycheck.gstatic.com", "clients3.google.com", "clients4.google.com"], []),
    ("Gemini", 15, ["Google"], ["AI"],
     ["gemini.google.com", "bard.google.com", "generativelanguage.googleapis.com",
      "aistudio.google.com"], []),

    # -- Meta --------------------------------------------------------------
    ("Facebook", 10, ["Meta", "Facebook"], ["Social", "Tracking"],
     ["facebook.com", "fbcdn.net", "fbsbx.com", "fb.com", "fb.me", "facebook.net",
      "messenger.com", "m.me"], []),
    ("Instagram", 10, ["Meta", "Instagram"], ["Social"],
     ["instagram.com", "cdninstagram.com", "ig.me"], []),
    ("WhatsApp", 10, ["Meta", "WhatsApp"], ["Messaging"],
     ["whatsapp.com", "whatsapp.net", "wa.me"], []),
    ("Threads", 12, ["Meta"], ["Social"], ["threads.net", "threads.com"], []),

    # -- other social ------------------------------------------------------
    ("TikTok", 10, ["TikTok"], ["Social", "Video"],
     ["tiktok.com", "tiktokcdn.com", "tiktokv.com", "byteoversea.com", "musical.ly",
      "ibytedtos.com", "bytedance.com", "tiktokcdn-us.com"], []),
    ("X / Twitter", 10, ["X"], ["Social", "News"],
     ["twitter.com", "x.com", "twimg.com", "t.co", "twitpic.com", "periscope.tv"], []),
    ("Reddit", 10, ["Reddit"], ["Social", "News"],
     ["reddit.com", "redd.it", "redditmedia.com", "redditstatic.com"], []),
    ("Snapchat", 10, ["Snapchat"], ["Social", "Messaging"],
     ["snapchat.com", "sc-cdn.net", "snap.com", "snapads.com"], []),
    ("LinkedIn", 10, ["LinkedIn"], ["Social", "Work"],
     ["linkedin.com", "licdn.com", "lnkd.in"], []),
    ("Pinterest", 10, ["Pinterest"], ["Social"], ["pinterest.com", "pinimg.com"], []),
    ("Tumblr", 12, ["Tumblr"], ["Social"], ["tumblr.com", "tumblr.co"], []),
    ("Mastodon", 15, ["Mastodon"], ["Social"], ["mastodon.social", "joinmastodon.org"], []),
    ("Bluesky", 15, ["Bluesky"], ["Social"], ["bsky.app", "bsky.social", "bsky.network"], []),

    # -- messaging ---------------------------------------------------------
    ("Discord", 10, ["Discord"], ["Messaging", "Gaming"],
     ["discord.com", "discordapp.com", "discord.gg", "discordapp.net", "discord.media"], []),
    ("Telegram", 10, ["Telegram"], ["Messaging"],
     ["telegram.org", "telegram.me", "t.me", "telesco.pe", "tdesktop.com"], []),
    ("Signal", 10, ["Signal"], ["Messaging"],
     ["signal.org", "whispersystems.org", "signal.art"], []),
    ("Viber", 12, ["Viber"], ["Messaging"], ["viber.com", "viber.net"], []),
    ("Slack", 10, ["Slack"], ["Messaging", "Work"],
     ["slack.com", "slack-edge.com", "slack-msgs.com", "slackb.com"], []),

    # -- streaming ---------------------------------------------------------
    ("Netflix", 10, ["Netflix"], ["Streaming", "Video"],
     ["netflix.com", "nflxvideo.net", "nflximg.net", "nflxext.com", "nflxso.net"], []),
    ("Disney+", 10, ["Disney"], ["Streaming", "Video"],
     ["disneyplus.com", "disney-plus.net", "dssott.com", "bamgrid.com", "disney.com"], []),
    ("HBO Max", 10, ["HBO"], ["Streaming", "Video"],
     ["hbomax.com", "max.com", "hbo.com", "hbomaxcdn.com"], []),
    ("Amazon Prime Video", 10, ["Amazon"], ["Streaming", "Video"],
     ["primevideo.com", "aiv-cdn.net", "aiv-delivery.net", "media-amazon.com"], []),
    ("Twitch", 10, ["Twitch"], ["Streaming", "Video", "Gaming"],
     ["twitch.tv", "ttvnw.net", "jtvnw.net", "twitchcdn.net"], []),
    ("Spotify", 10, ["Spotify"], ["Music", "Streaming"],
     ["spotify.com", "scdn.co", "spotifycdn.com", "spotilocal.com"], []),
    ("Apple Music", 12, ["Apple"], ["Music", "Streaming"],
     ["music.apple.com", "mzstatic.com", "itunes.apple.com"], []),
    ("SoundCloud", 15, ["SoundCloud"], ["Music", "Streaming"],
     ["soundcloud.com", "sndcdn.com"], []),
    ("Plex", 15, ["Plex"], ["Streaming", "Video"], ["plex.tv", "plex.direct"], []),
    ("Vimeo", 15, ["Vimeo"], ["Video", "Streaming"], ["vimeo.com", "vimeocdn.com"], []),

    # -- Apple -------------------------------------------------------------
    ("Apple Services", 20, ["Apple"], ["OS Service", "Cloud"],
     ["apple.com", "icloud.com", "icloud-content.com", "cdn-apple.com", "apple-cloudkit.com",
      "push.apple.com", "aaplimg.com", "me.com", "mac.com", "appleid.apple.com"], []),
    ("Apple Software Update", 15, ["Apple"], ["Software Update"],
     ["swcdn.apple.com", "swscan.apple.com", "swquery.apple.com", "appldnld.apple.com",
      "updates.cdn-apple.com", "gs.apple.com"], []),
    ("Apple Telemetry", 14, ["Apple"], ["Telemetry"],
     ["metrics.apple.com", "iadsdk.apple.com", "app-measurement.com",
      "securemetrics.apple.com", "xp.apple.com"], []),

    # -- Microsoft ---------------------------------------------------------
    ("Microsoft Services", 20, ["Microsoft"], ["Cloud", "Work"],
     ["microsoft.com", "microsoftonline.com", "live.com", "outlook.com", "office.com",
      "office365.com", "sharepoint.com", "onedrive.com", "msn.com", "bing.com",
      "microsoftedge.com", "azureedge.net", "msauth.net", "msftauth.net"], []),
    ("Windows Update", 15, ["Microsoft"], ["Software Update"],
     ["windowsupdate.com", "update.microsoft.com", "delivery.mp.microsoft.com",
      "tlu.dl.delivery.mp.microsoft.com", "windowsupdate.microsoft.com",
      "do.dsp.mp.microsoft.com"], []),
    ("Microsoft Telemetry", 14, ["Microsoft"], ["Telemetry", "Tracking"],
     ["vortex.data.microsoft.com", "telemetry.microsoft.com", "watson.telemetry.microsoft.com",
      "settings-win.data.microsoft.com", "events.data.microsoft.com",
      "telecommand.telemetry.microsoft.com"],
     []),
    ("Microsoft Teams", 12, ["Microsoft"], ["Work", "Messaging"],
     ["teams.microsoft.com", "teams.live.com", "skype.com", "skypeassets.com"], []),
    ("Xbox", 12, ["Microsoft", "Xbox"], ["Gaming"],
     ["xbox.com", "xboxlive.com", "xboxservices.com"], []),
    ("Copilot", 12, ["Microsoft"], ["AI"],
     ["copilot.microsoft.com", "githubcopilot.com", "copilot.github.com"], []),

    # -- AI ----------------------------------------------------------------
    ("OpenAI", 10, ["OpenAI"], ["AI"],
     ["openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com", "chat.openai.com"], []),
    ("Anthropic", 10, ["Anthropic"], ["AI"],
     ["anthropic.com", "claude.ai", "claudeusercontent.com"], []),
    ("Perplexity", 12, ["Perplexity"], ["AI", "Search"], ["perplexity.ai"], []),
    ("Other AI services", 25, [], ["AI"],
     ["mistral.ai", "huggingface.co", "midjourney.com", "stability.ai", "cohere.com",
      "deepseek.com", "x.ai", "grok.com", "runwayml.com", "elevenlabs.io"], []),

    # -- search ------------------------------------------------------------
    ("Bing", 20, ["Microsoft", "Bing"], ["Search"], ["bing.com", "bingapis.com"], []),
    ("DuckDuckGo", 15, ["DuckDuckGo"], ["Search"],
     ["duckduckgo.com", "duck.com", "improving.duckduckgo.com"], []),
    ("Other search engines", 25, [], ["Search"],
     ["yandex.ru", "yandex.com", "baidu.com", "ecosia.org", "startpage.com", "brave.com",
      "qwant.com", "search.marginalia.nu", "mojeek.com"], []),

    # -- advertising / tracking -------------------------------------------
    ("Ad networks", 20, [], ["Advertising"],
     ["adnxs.com", "adsrvr.org", "criteo.com", "criteo.net", "taboola.com", "outbrain.com",
      "pubmatic.com", "rubiconproject.com", "openx.net", "casalemedia.com", "smartadserver.com",
      "adform.net", "adcolony.com", "applovin.com", "unityads.unity3d.com", "inmobi.com",
      "moatads.com", "scorecardresearch.com", "zemanta.com", "sharethrough.com",
      "teads.tv", "yieldmo.com", "media.net", "revcontent.com", "mgid.com", "adsafeprotected.com"],
     [("contains", "adservice"), ("contains", "adserver")]),
    ("Analytics", 20, [], ["Analytics", "Tracking"],
     ["google-analytics.com", "analytics.google.com", "segment.com", "segment.io",
      "mixpanel.com", "amplitude.com", "hotjar.com", "fullstory.com", "heap.io",
      "matomo.cloud", "plausible.io", "statcounter.com", "quantserve.com", "chartbeat.com",
      "newrelic.com", "nr-data.net", "bugsnag.com", "sentry.io", "logrocket.com",
      "clarity.ms", "mouseflow.com", "crazyegg.com", "optimizely.com"], []),
    ("Trackers", 22, [], ["Tracking"],
     ["branch.io", "adjust.com", "appsflyer.com", "kochava.com", "singular.net",
      "onesignal.com", "urbanairship.com", "airship.com", "braze.com", "iterable.com",
      "clevertap.com", "leanplum.com", "swrve.com", "mparticle.com", "tealiumiq.com",
      "krxd.net", "demdex.net", "everesttech.net", "omtrdc.net", "adobedtm.com",
      "bluekai.com", "exelator.com", "rlcdn.com", "crwdcntrl.net", "agkn.com"], []),
    ("Telemetry endpoints", 24, [], ["Telemetry"],
     ["crashlytics.com", "app-measurement.com", "firebase-settings.crashlytics.com",
      "device-metrics-us.amazon.com", "metrics.roku.com", "logs.netflix.com",
      "telemetry.mozilla.org", "incoming.telemetry.mozilla.org"],
     [("contains", "telemetry"), ("startswith", "metrics.")]),

    # -- shopping ----------------------------------------------------------
    ("Amazon", 15, ["Amazon"], ["Shopping"],
     ["amazon.com", "amazon.de", "amazon.co.uk", "amazon.it", "amazon.fr", "amazon.es",
      "amazon.pl", "ssl-images-amazon.com", "amazonpay.com"], []),
    ("Online marketplaces", 20, [], ["Shopping"],
     ["ebay.com", "ebay.de", "aliexpress.com", "alibaba.com", "temu.com", "shein.com",
      "etsy.com", "wish.com", "asos.com", "zalando.com", "zalando.hu", "ikea.com",
      "decathlon.hu", "mediamarkt.hu", "alza.hu", "emag.hu", "arukereso.hu",
      "jofogas.hu", "vatera.hu", "hardverapro.hu", "notebook.hu", "edigital.hu"], []),

    # -- gaming ------------------------------------------------------------
    ("Steam", 12, ["Steam", "Valve"], ["Gaming", "Software Update"],
     ["steampowered.com", "steamcommunity.com", "steamstatic.com", "steamcontent.com",
      "valvesoftware.com", "steamserver.net"], []),
    ("Epic Games", 12, ["Epic Games"], ["Gaming"],
     ["epicgames.com", "unrealengine.com", "fortnite.com", "epicgames.dev",
      "helpshift.com"], []),
    ("PlayStation", 12, ["Sony", "PlayStation"], ["Gaming"],
     ["playstation.com", "playstation.net", "sonyentertainmentnetwork.com", "sony.com"], []),
    ("Nintendo", 12, ["Nintendo"], ["Gaming"],
     ["nintendo.com", "nintendo.net", "nintendo-europe.com", "nintendowifi.net"], []),
    ("Other game services", 22, [], ["Gaming"],
     ["riotgames.com", "leagueoflegends.com", "blizzard.com", "battle.net", "ea.com",
      "origin.com", "ubisoft.com", "ubi.com", "roblox.com", "rbxcdn.com", "minecraft.net",
      "mojang.com", "gog.com", "itch.io", "curseforge.com", "supercell.com",
      "king.com", "rockstargames.com"], []),

    # -- work / developer --------------------------------------------------
    ("GitHub", 12, ["GitHub"], ["Developer", "Work"],
     ["github.com", "githubusercontent.com", "github.io", "githubassets.com", "ghcr.io"], []),
    ("GitLab", 15, ["GitLab"], ["Developer", "Work"], ["gitlab.com", "gitlab.io"], []),
    ("Atlassian", 15, ["Atlassian"], ["Work"],
     ["atlassian.com", "atlassian.net", "jira.com", "bitbucket.org", "trello.com"], []),
    ("Zoom", 12, ["Zoom"], ["Work", "Video"], ["zoom.us", "zoomgov.com", "zoom.com"], []),
    ("Notion", 15, ["Notion"], ["Work"], ["notion.so", "notion.com", "notion-static.com"], []),
    ("Developer services", 25, [], ["Developer"],
     ["npmjs.org", "npmjs.com", "pypi.org", "pythonhosted.org", "docker.io", "docker.com",
      "rubygems.org", "packagist.org", "maven.org", "crates.io", "stackoverflow.com",
      "stackexchange.com", "readthedocs.io", "jsdelivr.net", "unpkg.com", "cdnjs.com",
      "vercel.app", "netlify.app", "heroku.com", "digitalocean.com"], []),

    # -- cloud / CDN -------------------------------------------------------
    ("Amazon Web Services", 30, ["Amazon", "AWS"], ["Cloud"],
     ["amazonaws.com", "awsstatic.com", "aws.amazon.com", "cloudfront.net"], []),
    ("Microsoft Azure", 30, ["Microsoft", "Azure"], ["Cloud"],
     ["azure.com", "azurewebsites.net", "windows.net", "azure-api.net", "azurefd.net"], []),
    ("Cloudflare", 30, ["Cloudflare"], ["CDN", "Cloud"],
     ["cloudflare.com", "cloudflare.net", "cloudflare-dns.com", "cf-ipfs.com", "workers.dev",
      "pages.dev", "cloudflareinsights.com"], []),
    ("Other CDNs", 32, [], ["CDN"],
     ["akamai.net", "akamaized.net", "akamaiedge.net", "akamaihd.net", "edgekey.net",
      "edgesuite.net", "fastly.net", "fastlylb.net", "llnwd.net", "stackpathdns.com",
      "b-cdn.net", "bunnycdn.com", "cdn77.org", "kxcdn.com", "cachefly.net"], []),
    ("File sync & sharing", 25, [], ["File Sharing", "Cloud"],
     ["dropbox.com", "dropboxusercontent.com", "box.com", "mega.nz", "mediafire.com",
      "wetransfer.com", "pcloud.com", "sync.com", "backblaze.com", "b2-api.backblazeb2.com"], []),

    # -- news --------------------------------------------------------------
    ("International news", 25, [], ["News"],
     ["bbc.co.uk", "bbc.com", "cnn.com", "nytimes.com", "theguardian.com", "reuters.com",
      "apnews.com", "bloomberg.com", "ft.com", "wsj.com", "aljazeera.com", "dw.com",
      "spiegel.de", "lemonde.fr", "economist.com", "npr.org"], []),
    ("Hungarian news", 25, ["Hungary"], ["News"],
     ["index.hu", "telex.hu", "hvg.hu", "444.hu", "24.hu", "origo.hu", "portfolio.hu",
      "nepszava.hu", "magyarnemzet.hu", "rtl.hu", "blikk.hu", "hirado.hu", "atv.hu",
      "napi.hu", "penzcentrum.hu", "hwsw.hu", "pcworld.hu", "sg.hu"], []),

    # -- finance -----------------------------------------------------------
    ("Payment providers", 20, [], ["Finance"],
     ["paypal.com", "paypalobjects.com", "stripe.com", "stripecdn.com", "revolut.com",
      "wise.com", "transferwise.com", "klarna.com", "adyen.com", "barion.com",
      "simplepay.hu", "otpbank.hu", "otpportalok.hu", "kh.hu", "erstebank.hu",
      "raiffeisen.hu", "mbhbank.hu", "unicreditbank.hu", "gránitbank.hu"], []),
    ("Crypto", 25, [], ["Finance"],
     ["coinbase.com", "binance.com", "kraken.com", "blockchain.com", "crypto.com",
      "coingecko.com", "coinmarketcap.com"], []),

    # -- IoT / smart home --------------------------------------------------
    ("Home Assistant", 10, ["Home Assistant"], ["IoT", "Work"],
     ["home-assistant.io", "hass.io", "nabucasa.com", "ui.nabu.casa",
      "home-assistant.net", "hacs.xyz"], []),
    ("Smart home vendors", 20, [], ["IoT"],
     ["tuya.com", "tuyaeu.com", "tuyaus.com", "shelly.cloud", "shelly.cloud.allterco.com",
      "sonoff.tech", "coolkit.cc", "ewelink.cc", "meethue.com", "philips-hue.com",
      "hue.com", "ring.com", "nest.com", "wyze.com", "tp-link.com", "tplinkcloud.com",
      "kasasmart.com", "ubnt.com", "ui.com", "reolink.com", "dahuasecurity.com",
      "hikvision.com", "ezvizlife.com", "arlo.com", "sonos.com", "ikea.net",
      "shelly.com", "tasmota.com", "esphome.io", "zigbee2mqtt.io", "netatmo.com",
      "daikin.eu", "midea.com", "bosch-smarthome.com"], []),
    ("Network time & connectivity", 22, [], ["OS Service"],
     ["pool.ntp.org", "ntp.org", "time.windows.com", "time.apple.com", "time.google.com",
      "time.cloudflare.com", "msftconnecttest.com", "msftncsi.com",
      "connectivity-check.ubuntu.com", "detectportal.firefox.com",
      "captive.apple.com", "network-test.debian.org"], []),

    # -- OS / vendor -------------------------------------------------------
    ("Samsung", 20, ["Samsung"], ["OS Service", "Telemetry"],
     ["samsung.com", "samsungcloud.com", "samsungqbe.com", "samsungrm.net",
      "samsungosp.com", "samsungdm.com", "samsungacr.com"], []),
    ("Xiaomi", 20, ["Xiaomi"], ["OS Service", "Telemetry"],
     ["mi.com", "xiaomi.com", "miui.com", "xiaomi.net", "aliyuncs.com"], []),
    ("Linux distributions", 25, [], ["Software Update"],
     ["ubuntu.com", "canonical.com", "debian.org", "archlinux.org", "fedoraproject.org",
      "opensuse.org", "alpinelinux.org", "raspberrypi.org", "raspbian.org"], []),
    ("Mozilla", 20, ["Mozilla"], ["OS Service", "Software Update"],
     ["mozilla.org", "mozilla.net", "mozilla.com", "firefox.com", "services.mozilla.com"], []),

    # -- travel / food / misc ---------------------------------------------
    ("Travel", 25, [], ["Travel"],
     ["booking.com", "airbnb.com", "expedia.com", "tripadvisor.com", "ryanair.com",
      "wizzair.com", "lufthansa.com", "skyscanner.net", "kayak.com", "mav.hu",
      "volanbusz.hu", "bkk.hu"], []),
    ("Food delivery", 25, [], ["Food"],
     ["wolt.com", "foodpanda.hu", "foodora.com", "ubereats.com", "bolt.eu",
      "deliveryhero.com"], []),
    ("Maps & navigation", 25, [], ["Travel"],
     ["waze.com", "openstreetmap.org", "mapbox.com", "here.com", "tomtom.com",
      "maps.google.com", "maps.gstatic.com"], []),
    ("Weather", 25, [], ["Weather"],
     ["openweathermap.org", "weather.com", "accuweather.com", "met.no", "idokep.hu",
      "koponyeg.hu", "metnet.hu", "weatherapi.com", "tomorrow.io"], []),
    ("Education", 25, [], ["Education"],
     ["wikipedia.org", "wikimedia.org", "wiktionary.org", "khanacademy.org",
      "coursera.org", "udemy.com", "edx.org", "duolingo.com", "brilliant.org"], []),
    ("Sports", 25, [], ["Sports"],
     ["espn.com", "uefa.com", "fifa.com", "formula1.com", "nemzetisport.hu",
      "eurosport.com", "flashscore.com", "sofascore.com"], []),
    ("Email providers", 25, [], ["Email"],
     ["protonmail.com", "proton.me", "tutanota.com", "fastmail.com", "zoho.com",
      "mailchimp.com", "sendgrid.net", "mailgun.org", "postmarkapp.com",
      "freemail.hu", "citromail.hu"], []),
    ("Security & VPN", 25, [], ["Security"],
     ["nordvpn.com", "expressvpn.com", "mullvad.net", "protonvpn.com", "wireguard.com",
      "tailscale.com", "1password.com", "bitwarden.com", "lastpass.com",
      "malwarebytes.com", "virustotal.com", "eset.com", "kaspersky.com",
      "bitdefender.com", "avast.com", "avg.com"], []),
    ("Health", 25, [], ["Health"],
     ["webmd.com", "mayoclinic.org", "nhs.uk", "hazipatika.com", "webbeteg.hu"], []),
    ("Hungarian government", 20, ["Hungary"], ["Government"],
     ["gov.hu", "magyarorszag.hu", "nav.gov.hu", "ekozig.hu", "kormany.hu"], []),
    ("Hungarian telecom", 22, ["Hungary"], ["OS Service"],
     ["telekom.hu", "vodafone.hu", "yettel.hu", "digi.hu", "invitel.hu", "upc.hu"], []),

    # -- adult -------------------------------------------------------------
    # Kept short and factual; AdGuard's own parental-control filters remain the
    # authoritative source. This only labels traffic for reporting.
    ("Adult content", 18, [], ["Adult"],
     ["pornhub.com", "xvideos.com", "xhamster.com", "redtube.com", "youporn.com",
      "onlyfans.com", "stripchat.com", "chaturbate.com", "xnxx.com", "brazzers.com"], []),
]


def build() -> dict[str, object]:
    tag_names: set[str] = set()
    category_names: set[str] = set()
    rules: list[dict[str, object]] = []

    for name, priority, tags, categories, suffixes, extra in RULES:
        conditions: list[dict[str, str]] = [
            {"field": "domain", "operator": "suffix", "value": suffix} for suffix in suffixes
        ]
        conditions += [
            {"field": "domain", "operator": operator, "value": value} for operator, value in extra
        ]
        if not conditions:
            raise ValueError(f"rule {name!r} has no conditions")

        tag_refs = [{"name": tag, "kind": "tag"} for tag in tags]
        tag_refs += [{"name": category, "kind": "category"} for category in categories]
        if not tag_refs:
            raise ValueError(f"rule {name!r} has no tags")

        tag_names.update(tags)
        category_names.update(categories)
        rules.append(
            {
                "name": name,
                "priority": priority,
                "match_mode": "any",
                "enabled": True,
                "conditions": conditions,
                "tags": tag_refs,
            }
        )

    for category in category_names:
        if category not in CATEGORY_COLORS:
            raise ValueError(f"category {category!r} has no colour")

    tags = [
        {"name": name, "kind": "tag", "color": TAG_COLORS.get(name, "")}
        for name in sorted(tag_names)
    ]
    tags += [
        {"name": name, "kind": "category", "color": CATEGORY_COLORS[name]}
        for name in sorted(category_names)
    ]

    return {
        "version": 1,
        "description": "Built-in domain categorisation rules bundled with the app.",
        "tags": tags,
        "rules": rules,
    }


def main() -> None:
    payload = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=False)
        handle.write("\n")
    rules = payload["rules"]
    tags = payload["tags"]
    assert isinstance(rules, list) and isinstance(tags, list)
    print(f"Wrote {OUT} — {len(rules)} rules, {len(tags)} tags/categories")


if __name__ == "__main__":
    main()
