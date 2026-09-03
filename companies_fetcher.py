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

import json
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
                # Occupies the old sector slot: the specific filing type, which
                # is the most informative short label available per item.
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
