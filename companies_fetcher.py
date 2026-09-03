"""
Fetcher for the Companies tab, sourced from Market Tide (https://markettide.in).

Market Tide reads the corporate announcements companies file with NSE and BSE,
drops the routine paperwork, and scores what is left. Its /api/announcements
endpoint is public and unauthenticated, and the default (curated) scope returns
the filings it considers worth reading.

Replaces the previous Tipsheet integration: tipsheet.markets stopped resolving
in DNS in mid-2026 and the tab served a frozen snapshot for weeks before anyone
noticed, so this module treats staleness as a first-class failure (see
companies_cache_age_days) rather than letting the cache fallback hide it.

What we take and what we deliberately leave behind
--------------------------------------------------
Market Tide's terms draw an explicit line: the underlying filings are public
exchange documents that they do not claim to own, while their summaries,
scoring and categorisation are their own work. So the card is built from the
filing's own facts — company, ticker, exchange, date, filing type and a link to
the original PDF — plus their market-cap band and tag for filtering. Their
prose fields (summary, why_it_matters, impact, key_numbers) are fetched but
never stored or rendered, and every view credits Market Tide with a link back.

Mirrors the resilient live-fetch-with-cache-fallback pattern of paper_fetcher.py:
a successful fetch refreshes static/companies_cache.json; on failure or empty
response the caller loads the cache so a CI hiccup never blanks the tab.
"""

import html
import json
import re
import urllib.request
from datetime import datetime, timedelta

from articles import IST_TZ
from config import (
    COMPANIES_ANNOUNCEMENTS_URL,
    COMPANIES_FETCH_TIMEOUT,
    COMPANIES_FRESHNESS_DAYS,
    COMPANIES_MAX_ITEMS,
    COMPANIES_SITE_BASE,
    DEFAULT_USER_AGENT,
)

COMPANIES_FEED_ID = "markettide"
COMPANIES_SOURCE_LABEL = "Market Tide"

# Cap-tier labels in display order. Market Tide bands by market cap in rupees
# crore; these are the thresholds its own dashboard filters on ("Above Rs 1
# lakh cr", "Rs 50,000 cr - 1 lakh cr", and so on down). Items carry a raw
# `mcap` number rather than a band, so the banding happens here — one request
# for everything instead of one request per band.
CAP_TIERS = ["Mega cap", "Large cap", "Mid cap", "Small cap", "Micro cap"]

CAP_BANDS = (
    (100_000, "Mega cap"),
    (50_000, "Large cap"),
    (10_000, "Mid cap"),
    (1_000, "Small cap"),
    (0, "Micro cap"),
)

# Fields that are Market Tide's own editorial work. Fetched as part of the
# payload, never persisted to the cache and never rendered.
RESERVED_FIELDS = ("summary", "why_it_matters", "impact", "key_numbers")


def cap_for_mcap(mcap):
    """Map a market cap in rupees crore to a display tier."""
    if not isinstance(mcap, (int, float)) or mcap <= 0:
        return ""
    for floor, label in CAP_BANDS:
        if mcap >= floor:
            return label
    return ""


# Lead-ins that carry no information. The filing's own headline is public
# (Market Tide's terms reserve only their summaries), but exchange filings bury
# the substance behind stock phrasing: 264 of ~1,200 headlines open with
# "<Company> has informed the Exchange about", another 98 with "The Exchange has
# received...". Stripping these is what turns the headline into a usable subtitle.
_LEADIN_PATTERNS = [
    # "<Company> has informed the Exchange about/regarding/that/of ..."
    re.compile(r"^.{0,90}?\bha(?:s|d)\s+informed\s+the\s+exchange\s*"
               r"(?:about|regarding|that|of|on)?\s*[:,-]?\s*", re.I),
    # "The Exchange has received the disclosure under ..."
    re.compile(r"^the\s+exchange\s+ha(?:s|d)\s+received\s+(?:the\s+)?", re.I),
    # "Disclosure under Regulation 30 of SEBI (LODR) Regulations, 2015 - <substance>"
    re.compile(r"^(?:update\s+on\s+)?disclosure\s+under\s+regulation[^-–—]*"
               r"(?:regulations?,?\s*\d{4})?\s*[-–—:]\s*", re.I),
    # "Pursuant to Regulation 30 of ... , <substance>"
    re.compile(r"^pursuant\s+to\s+regulation[^,]{0,120},\s*", re.I),
    re.compile(r"^we\s+(?:wish|would\s+like)\s+to\s+inform\s+(?:you\s+)?(?:that\s+)?", re.I),
    re.compile(r"^(?:please\s+)?find\s+(?:attached|enclosed)\s*(?:herewith)?\s*", re.I),
    re.compile(r"^please\s+find\s+(?:attached|enclosed)\s*(?:herewith)?\s*", re.I),
    re.compile(r"^(?:the\s+)?intimation\s*(?:regarding|of|on|-|:)\s*", re.I),
    # "<Company> has submitted to the Exchange a copy of <substance>"
    re.compile(r"^.{0,90}?\bha(?:s|ve|d)\s+submitted\s+to\s+the\s+exchange\s+"
               r"(?:a\s+copy\s+of\s+)?", re.I),
    # Stripping the company can leave the auxiliary stranded at the front.
    re.compile(r"^(?:ha(?:s|ve|d)|is|are|was|were)\s+", re.I),
    # Cutting a citation at an interior comma strands its year: "2015, we are...".
    re.compile(r"^\d{4}\s*,\s*", re.I),
    # Quoted internal list items keep their enumerator: "'3. ESOP Grant ...'".
    re.compile(r"^\d{1,2}\s*[.)]\s+", re.I),
    re.compile(r"^(?:we\s+are\s+)?enclosing\s+herewith\s+(?:a\s+)?", re.I),
    re.compile(r"^(?:this\s+is\s+further\s+to|in\s+continuation\s+(?:to|of)|with\s+reference\s+to)\s+", re.I),
    re.compile(r"^announcement\s+under\s+regulation\s*\d*\s*[.:-]?\s*", re.I),
]

# What is left after stripping is sometimes still nothing. These are not worth
# showing as a subtitle, so the filing category is used instead.
_EMPTY_AFTER_STRIP = {
    "", "-", "as enclosed", "as enclosed.", "as attached", "as attached.",
    "update", "'update'", "updates", "general", "n/a", "na", "nil",
    "read less..", "not applicable", "as per attachment", "as per attachment.",
    "as attached herewith", "as per the attachment", "attached", "attached.",
}


# Some lead-ins ARE the news — dropping the verb would lose it. Rewrite instead.
_REWRITE_PATTERNS = [
    # "A press release dated 03 September 2026, titled \"X\"" -> X. Also catches
    # "...we are enclosing herewith a Press Release titled 'X'".
    # The dateline can carry more than one comma ("September 03, 2026, titled"),
    # so match it lazily rather than up to the first comma.
    (re.compile(r"^.{0,120}?press\s+release\s*(?:dated\s+.{0,45}?)?\s*"
                r"titled\s*[\"'\u2018\u201c]?(?P<t>[^\"'\u2019\u201d]{6,})", re.I),
     r"\g<t>"),
    (re.compile(r"^the\s+exchange\s+ha(?:s|d)\s+sought\s+clarification\s+from\s+"
                r".{0,90}?(?=\bfor\b|\bwith\b|$)", re.I),
     "Exchange sought clarification "),
]

# Regulation citations tacked onto the end carry no information for a reader.
_TRAILING_NOISE = [
    re.compile(r"\s*(?:pursuant\s+to|under|with\s+respect\s+to|in\s+terms\s+of|read\s+with)"
               r"\s+(?:regulation|schedule)\b.*$", re.I),
    re.compile(r"\s*of\s+the\s+SEBI\s*\(?(?:LODR|Listing\s+Obligations).*$", re.I),
    re.compile(r"\s*\(?(?:LODR|Listing\s+Obligations\s+and\s+Disclosure\s+Requirements)"
               r"\)?\s*Regulations?,?\s*\d{4}\.?$", re.I),
]

# If this is all that survives, it was a citation with no substance. Kept
# deliberately flat and length-bounded: a nested quantifier over an overlapping
# character class here backtracks catastrophically on long citation chains.
_CITATION_ONLY = re.compile(
    r"^(?:(?:disclosure|intimation|announcement|submission|compliance)\s+)?"
    r"(?:(?:pursuant\s+to|under|in\s+terms\s+of|read\s+with|as\s+per|of)\s+)?"
    r"(?:regulation|reg\.?|schedule|clause|para)\b[\s\d.,()a-z]{0,120}$", re.I)


def _sentence_case(text):
    """Exchange filings are often shouted in ALL CAPS. Tame them."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio < 0.75:
        return text
    out = text.lower()
    # Restore the obvious acronyms rather than leaving "sebi" and "nclt".
    for acr in ("SEBI", "LODR", "NCLT", "NCLAT", "RBI", "IRDAI", "CCI", "GST",
                "USD", "INR", "NCD", "NCRPS", "ESOP", "AGM", "EGM", "IPO",
                "QIP", "MOU", "CIRP", "AI", "IT", "CEO", "CFO", "MD", "NSE", "BSE"):
        out = re.sub(rf"\b{acr.lower()}\b", acr, out)
    return out[:1].upper() + out[1:]


def _strip_company_prefix(text, company):
    """Drop a leading restatement of the company name — the title already has it."""
    if not company:
        return text
    # Compare on words, ignoring the Ltd/Limited/Pvt suffix noise.
    stop = {"ltd", "ltd.", "limited", "pvt", "private", "the", "and", "&", "corporation", "co", "co."}
    words = [w for w in re.split(r"[^A-Za-z0-9&]+", company) if w and w.lower() not in stop]
    if not words:
        return text
    # Consume as many leading company words as actually match, in order.
    pattern = r"^\s*(?:the\s+)?" + r"[^A-Za-z0-9]*".join(re.escape(w) for w in words[:4])
    stripped = re.sub(pattern + r"[^A-Za-z0-9]*(?:ltd\.?|limited|pvt\.?|private)?\s*",
                      "", text, count=1, flags=re.I)
    if stripped == text:
        return text
    # Removing the name can leave a fragment that reads worse than keeping it.
    leftover = stripped.lstrip(" \t-–—:;,.\"'")
    if leftover.startswith("(") or sum(1 for c in leftover if c.isalpha()) < 6:
        return text
    return stripped


def filing_subtitle(headline, company="", category=""):
    """Turn a filing headline into a subtitle that says what the update is about.

    The card title is the company, so this must not repeat it, and it must not
    be exchange boilerplate. Falls back to the filing category when the headline
    reduces to nothing useful.
    """
    text = html.unescape(str(headline or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return (category or "").strip()

    text = _sentence_case(text)

    # Rewrites before strips: these lead-ins carry the news in the verb. Applied
    # twice because the feed itself sometimes doubles them.
    for _ in range(2):
        for pat, replacement in _REWRITE_PATTERNS:
            text = pat.sub(replacement, text, count=1).strip()

    # Lead-ins first, then any remaining company restatement, then lead-ins
    # again — "<Company> has informed the Exchange" leaves a second layer often.
    # Quotes are stripped each pass: filings often quote the enclosed text
    # verbatim ("... regarding '3. ESOP Grant adjustment ...'"), and a leading
    # quote stops the enumerator and lead-in patterns from anchoring at all.
    for _ in range(2):
        text = text.strip(" \t\"'‘’“”")
        for pat in _LEADIN_PATTERNS:
            text = pat.sub("", text, count=1).strip()
        text = text.strip(" \t\"'‘’“”")
        text = _strip_company_prefix(text, company).strip()

    # Drop trailing regulation citations, but never everything: if the citation
    # is all there is, the category is the better answer.
    for pat in _TRAILING_NOISE:
        trimmed = pat.sub("", text).strip(" \t-–—:;,.")
        if len(trimmed) >= 12:
            text = trimmed

    text = text.strip(" \t-–—:;,.\"'")

    # Backstop for every stripping rule: a subtitle with no words is not a
    # subtitle. Cutting a citation at an interior comma can leave just a year.
    if sum(1 for c in text if c.isalpha()) < 3:
        return (category or "").strip()

    if (text.lower() in _EMPTY_AFTER_STRIP or len(text) < 4
            or _CITATION_ONLY.match(text)):
        return (category or "").strip()

    return text[:1].upper() + text[1:]


def _parse_markettide_date(day, time_str):
    """Combine Market Tide's date ("2026-09-03") and time ("03 Sep, 11:59").

    The time field is display text, not a parseable stamp on its own, so the
    date carries the day and the time is only mined for HH:MM. A filing with an
    unreadable time still keeps its date rather than being dropped.
    """
    if not day:
        return None
    try:
        base = datetime.strptime(str(day).strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None

    hour = minute = 0
    if time_str:
        tail = str(time_str).split(",")[-1].strip()
        parts = tail.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1][:2].isdigit():
            hour, minute = int(parts[0]), int(parts[1][:2])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                hour = minute = 0

    return base.replace(hour=hour, minute=minute, tzinfo=IST_TZ)


def _extract_items(payload):
    """/api/announcements returns {items: [...]}; tolerate a bare array too."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return payload["items"]
        for value in payload.values():
            if isinstance(value, list):
                return value
    return []


def parse_companies(payload, now=None):
    """Map the announcements payload into normalized company-filing objects."""
    now = now or datetime.now(IST_TZ)
    cutoff = now - timedelta(days=COMPANIES_FRESHNESS_DAYS)

    companies = []
    seen_keys = set()
    for item in _extract_items(payload):
        if not isinstance(item, dict):
            continue

        company = (item.get("company") or "").strip()
        # The filing PDF is the primary link: it is the public document itself.
        # page_url points at the exchange quote page, which is a weaker target.
        link = (item.get("pdf_url") or item.get("page_url") or "").strip()
        if not company or not link:
            continue

        # A filing can be filed on both exchanges; id is stable, link is not.
        dedupe_key = (item.get("id") or link).strip().lower()
        if dedupe_key in seen_keys:
            continue

        date_value = _parse_markettide_date(item.get("date") or item.get("day"),
                                            item.get("time"))
        if date_value is not None and date_value < cutoff:
            continue

        try:
            score = int(item.get("score")) if item.get("score") is not None else 0
        except (TypeError, ValueError):
            score = 0

        mcap = item.get("mcap")
        try:
            mcap = float(mcap) if mcap is not None else None
        except (TypeError, ValueError):
            mcap = None

        seen_keys.add(dedupe_key)
        companies.append(
            {
                # The company is what the card leads with. The filing's own
                # headline is regulatory boilerplate ("Disclosure under
                # Regulation 30 of SEBI (LODR)...") repeated across hundreds of
                # filings, so it reads as the description, not the title.
                "title": company,
                "link": link,
                "source": COMPANIES_SOURCE_LABEL,
                "source_url": COMPANIES_SITE_BASE,
                "publisher": COMPANIES_SOURCE_LABEL,
                "description": (item.get("headline") or "").strip(),
                "date": date_value,
                "time": date_value.strftime("%I:%M %p").lstrip("0") if date_value else "",
                "ticker": (item.get("ticker") or "").strip(),
                "exchange": (item.get("exchange") or "").strip(),
                # What the update is actually about, from the filing's own
                # headline. The card title is the company, so this must not
                # restate it — see filing_subtitle().
                "subtitle": filing_subtitle(item.get("headline"), company,
                                            item.get("category")),
                # The specific filing type, kept as the subtitle's fallback and
                # for the data attributes.
                "sector": (item.get("category") or "").strip(),
                "cap": cap_for_mcap(mcap),
                "mcap": mcap,
                "category": (item.get("tag") or "").strip(),
                "score": score,
                "feed_id": COMPANIES_FEED_ID,
            }
        )

    # Default order: most consequential first (score desc), newest as tiebreak.
    epoch_ist = datetime(1970, 1, 1, tzinfo=IST_TZ)
    companies.sort(
        key=lambda c: (
            -c.get("score", 0),
            -((c.get("date") or epoch_ist).timestamp()),
        )
    )
    return companies[:COMPANIES_MAX_ITEMS]


def fetch_companies(url=COMPANIES_ANNOUNCEMENTS_URL, timeout=COMPANIES_FETCH_TIMEOUT,
                    now=None):
    """Fetch and parse Market Tide filings. Returns a list (empty on failure)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    return parse_companies(payload, now=now)


def save_companies_cache(cache_file, companies):
    """Persist companies to cache with ISO datetime serialization."""
    payload = {
        "generated_at": datetime.now(IST_TZ).isoformat(),
        "source": COMPANIES_SOURCE_LABEL,
        "companies": [
            {
                **{k: v for k, v in c.items() if k not in RESERVED_FIELDS},
                "date": c["date"].isoformat() if c.get("date") else None,
            }
            for c in (companies or [])
        ],
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload["generated_at"]


def load_companies_cache(cache_file):
    """Load cached companies; returns (companies, generated_at)."""
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return [], ""

    if isinstance(payload, list):
        raw_items, generated_at = payload, ""
    else:
        raw_items = payload.get("companies", [])
        generated_at = payload.get("generated_at", "")

    companies = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        company = dict(item)
        date_raw = company.get("date")
        if date_raw:
            try:
                company["date"] = datetime.fromisoformat(date_raw)
            except ValueError:
                company["date"] = None
        else:
            company["date"] = None
        companies.append(company)
    return companies, generated_at


def companies_cache_age_days(companies, now=None):
    """Days since the newest cached filing, or None if nothing is dated.

    Exists because the Tipsheet outage was invisible: the fetch failed, the
    cache fallback served two-month-old filings, and the run stayed green. The
    caller warns loudly once this passes the freshness window.
    """
    now = now or datetime.now(IST_TZ)
    stamps = []
    for c in companies or []:
        d = c.get("date")
        if isinstance(d, datetime):
            stamps.append(d if d.tzinfo else d.replace(tzinfo=IST_TZ))
    if not stamps:
        return None
    return (now - max(stamps)).days


if __name__ == "__main__":
    from collections import Counter

    from config import COMPANIES_CACHE_FILE

    items = fetch_companies()
    print(f"Fetched {len(items)} company filings from {COMPANIES_SOURCE_LABEL}")
    if items:
        print("By cap tier:", dict(Counter(c.get("cap") or "?" for c in items)))
        print("By exchange:", dict(Counter(c.get("exchange") or "?" for c in items)))
        print("Newest filing age (days):", companies_cache_age_days(items))
        save_companies_cache(COMPANIES_CACHE_FILE, items)
        print(f"Saved cache -> {COMPANIES_CACHE_FILE}")
